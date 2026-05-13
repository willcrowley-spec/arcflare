"""Salesforce metadata synchronization.

Pulls object describes, fields, flows, apex classes/triggers, validation rules,
workflow rules, approval processes, page layouts, flexipages, profiles, and permission
sets using the Metadata and Tooling APIs.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict
import re
import urllib.parse
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from requests.adapters import HTTPAdapter
from simple_salesforce import Salesforce
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_tokens
from app.models.connection import PlatformConnection
from app.models.licensing import OrgLicenseSnapshot, UserVelocitySnapshot
from app.models.metadata import (
    MetadataAutomation,
    MetadataComponent,
    MetadataDependency,
    MetadataField,
    MetadataObject,
)
from app.models.organization import Organization
from app.services.connectors.base import (
    PermissionMeta,
    PlatformObjectMeta,
    UsageData,
)
from app.services.salesforce.apex_parser.analyzer import analyze_apex_class, analyze_apex_trigger
from app.services.salesforce.mdapi_parser import (
    parse_approval_process,
    parse_custom_object,
    parse_flow,
    parse_workflow,
)
from app.services.salesforce.mdapi_retrieve import (
    MDAPIInsufficientAccessError,
    check_mdapi_access,
    retrieve_metadata,
)

if TYPE_CHECKING:
    from app.services.sync_event_log import SyncEventEmitter

logger = logging.getLogger(__name__)

DEFAULT_OBJECTS = [
    "Account",
    "Contact",
    "Opportunity",
    "Lead",
    "Case",
    "Task",
    "Event",
    "OpportunityLineItem",
    "Product2",
    "PricebookEntry",
    "Campaign",
    "CampaignMember",
]

_SAFE_CMDT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*__mdt$")


def _get_latest_api_version(instance_url: str, access_token: str) -> str:
    """Query the org's /services/data/ endpoint to get the latest supported API version."""
    import requests

    url = f"{instance_url}/services/data/"
    resp = requests.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
    resp.raise_for_status()
    versions = resp.json()
    latest = max(versions, key=lambda v: float(v["version"]))
    logger.info("sf_api_version_resolved version=%s", latest["version"])
    return latest["version"]


def get_sf_client(instance_url: str, access_token: str) -> Salesforce:
    """Create a Salesforce client using the org's latest API version."""
    instance = instance_url.replace("https://", "").replace("http://", "")
    version = _get_latest_api_version(instance_url, access_token)
    sf = Salesforce(instance=instance, session_id=access_token, version=version)
    adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
    sf.session.mount("https://", adapter)
    return sf


_RETRYABLE_STATUSES = {429, 500, 502, 503}


def _sf_request_with_retry(fn, *args, max_retries: int = 3, **kwargs):
    """Retry on transient Salesforce API errors with exponential backoff."""
    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            status = getattr(e, "status", None) or getattr(e, "code", None)
            if attempt < max_retries and status in _RETRYABLE_STATUSES:
                wait = 2 ** (attempt + 1)
                logger.warning("sf_retry attempt=%d wait=%ds error=%s", attempt + 1, wait, e)
                time.sleep(wait)
            else:
                raise


def _tooling_query_all(sf: Salesforce, soql: str) -> list[dict]:
    """Execute a Tooling API SOQL query with pagination."""
    encoded = urllib.parse.quote(soql)
    result = sf.toolingexecute(f"query/?q={encoded}")
    records = result.get("records", [])
    while result.get("nextRecordsUrl"):
        next_url = result["nextRecordsUrl"]
        if "/tooling/" in next_url:
            next_url = next_url.split("/tooling/")[1]
        result = sf.toolingexecute(next_url)
        records.extend(result.get("records", []))
    return records


def _rest_query_all(sf: Salesforce, soql: str) -> list[dict]:
    """Execute a Data API SOQL query with pagination (for objects not in Tooling)."""
    out: list[dict] = []
    result = sf.query(soql)
    out.extend(result.get("records", []))
    while not result.get("done") and result.get("nextRecordsUrl"):
        result = sf.query_more(result["nextRecordsUrl"], identifier_is_url=True)
        out.extend(result.get("records", []))
    return out


def _detect_namespace(api_name: str) -> tuple[bool, str | None]:
    parts = api_name.split("__")
    if len(parts) >= 3:
        return True, parts[0]
    return False, None


def _extract_fields(describe: dict) -> list[dict]:
    fields = []
    for f in describe.get("fields", []):
        fields.append(
            {
                "name": f.get("name", ""),
                "type": f.get("type", ""),
                "label": f.get("label", ""),
                "description": f.get("inlineHelpText", "") or "",
                "referenceTo": f.get("referenceTo", []),
                "nillable": f.get("nillable", True),
                "picklistValues": [
                    {"value": pv.get("value", ""), "active": pv.get("active", False)}
                    for pv in f.get("picklistValues", [])
                ],
            }
        )
    return fields


def _extract_relationships(describe: dict) -> list[dict]:
    rels = []
    for f in describe.get("fields", []):
        if f.get("type") == "reference" and f.get("referenceTo"):
            rel_type = "MasterDetail" if not f.get("nillable", True) else "Lookup"
            rels.append(
                {
                    "field_name": f.get("name", ""),
                    "targets": f.get("referenceTo", []),
                    "relationship_type": rel_type,
                }
            )
    return rels


def pull_object_list(sf: Salesforce) -> list[dict]:
    """Get all SObjects in the org."""
    result = sf.describe()
    return result.get("sobjects", [])


_COMPOSITE_BATCH_SIZE = 25


def _composite_batch_post(sf: Salesforce, subrequests: list[dict]) -> list[dict]:
    """POST a composite batch and return the list of subrequest results."""
    url = f"{sf.base_url.rstrip('/')}/composite/batch"
    headers = {
        "Authorization": f"Bearer {sf.session_id}",
        "Content-Type": "application/json",
    }
    payload = {"batchRequests": subrequests}
    resp = _sf_request_with_retry(
        sf.session.post, url, json=payload, headers=headers, timeout=120,
    )
    if resp.status_code >= 400:
        logger.error(
            "sf_composite_batch_error status=%d body=%s",
            resp.status_code,
            resp.text[:500],
        )
    resp.raise_for_status()
    limit_info = resp.headers.get("Sforce-Limit-Info")
    if limit_info:
        logger.info("sf_api_limit_info %s", limit_info)
    return resp.json().get("results", [])


def _parse_describe_result(describe: dict, obj_name: str) -> PlatformObjectMeta | None:
    """Convert a raw describe response dict into a PlatformObjectMeta."""
    api_name = describe.get("name", obj_name)
    is_custom = api_name.endswith("__c")
    is_managed, namespace = _detect_namespace(api_name)
    fields = _extract_fields(describe)
    relationships = _extract_relationships(describe)
    record_type_infos = [
        {
            "name": rt.get("name", ""),
            "developer_name": rt.get("developerName", ""),
            "is_active": rt.get("active", False),
            "is_master": rt.get("master", False),
            "record_type_id": rt.get("recordTypeId", ""),
        }
        for rt in describe.get("recordTypeInfos", [])
        if not rt.get("master", False)
    ]
    return PlatformObjectMeta(
        api_name=api_name,
        label=describe.get("label", api_name),
        field_count=len(fields),
        is_managed_package=is_managed,
        namespace_prefix=namespace,
        is_custom=is_custom,
        fields=fields,
        relationships=relationships,
        record_types=record_type_infos,
    )


def pull_object_describes(sf: Salesforce, objects: list[str] | None = None) -> list[PlatformObjectMeta]:
    """Pull describes for all (or specified) objects via Composite Batch API."""
    if objects is None:
        all_objects = pull_object_list(sf)
        custom = [
            o["name"]
            for o in all_objects
            if o.get("name", "").endswith("__c") and o.get("queryable")
        ]
        objects = DEFAULT_OBJECTS + custom

    ver = sf.sf_version
    batches: list[list[str]] = [
        objects[i : i + _COMPOSITE_BATCH_SIZE]
        for i in range(0, len(objects), _COMPOSITE_BATCH_SIZE)
    ]

    results: list[PlatformObjectMeta] = []
    for batch_idx, batch_names in enumerate(batches):
        subrequests = [
            {"method": "GET", "url": f"v{ver}/sobjects/{name}/describe"}
            for name in batch_names
        ]
        try:
            batch_results = _composite_batch_post(sf, subrequests)
        except Exception as e:
            logger.warning("sf_describe_batch_failed batch=%d error=%s", batch_idx, e)
            continue

        for name, sub_result in zip(batch_names, batch_results):
            status_code = sub_result.get("statusCode", 500)
            if status_code != 200:
                logger.warning(
                    "sf_describe_failed object=%s status=%s",
                    name,
                    status_code,
                )
                continue
            try:
                meta = _parse_describe_result(sub_result.get("result", {}), name)
                if meta:
                    results.append(meta)
            except Exception as e:
                logger.warning("sf_describe_parse_failed object=%s error=%s", name, e)

    logger.info(
        "sf_all_describes_complete count=%d batches=%d",
        len(results),
        len(batches),
    )
    return results



def pull_permission_sets(sf: Salesforce) -> list[PermissionMeta]:
    try:
        try:
            raw = _rest_query_all(
                sf,
                "SELECT Id,Name,Label,Description,IsCustom,NamespacePrefix "
                "FROM PermissionSet WHERE IsCustom=true",
            )
        except Exception as exc:
            logger.warning("sf_permission_sets_namespace_query_failed error=%s", exc)
            raw = _rest_query_all(
                sf, "SELECT Id,Name,Label,Description,IsCustom FROM PermissionSet WHERE IsCustom=true"
            )
        ps_ids = [ps["Id"] for ps in raw]
        perms_by_parent: dict[str, list[dict]] = {}

        for i in range(0, len(ps_ids), 200):
            batch = ps_ids[i : i + 200]
            id_list = ",".join(f"'{pid}'" for pid in batch)
            obj_soql = (
                f"SELECT Id,ParentId,SobjectType,"
                f"PermissionsRead,PermissionsCreate,PermissionsEdit,PermissionsDelete "
                f"FROM ObjectPermissions WHERE ParentId IN ({id_list})"
            )
            for op in _rest_query_all(sf, obj_soql):
                perms_by_parent.setdefault(op.get("ParentId", ""), []).append(op)

        results = []
        seen_api_names: set[str] = set()
        for ps in raw:
            ps_id = ps.get("Id", "")
            raw_name = ps.get("Name", "")
            namespace = ps.get("NamespacePrefix")
            api_name = f"{namespace}__{raw_name}" if namespace else raw_name
            if not api_name:
                continue
            if api_name in seen_api_names:
                logger.warning(
                    "sf_permission_set_duplicate_skipped api_name=%s id=%s",
                    api_name,
                    ps_id,
                )
                continue
            seen_api_names.add(api_name)
            obj_perms = [
                {
                    "object": op.get("SobjectType", ""),
                    "read": op.get("PermissionsRead", False),
                    "create": op.get("PermissionsCreate", False),
                    "edit": op.get("PermissionsEdit", False),
                    "delete": op.get("PermissionsDelete", False),
                }
                for op in perms_by_parent.get(ps_id, [])
            ]
            results.append(
                PermissionMeta(
                    api_name=api_name,
                    label=ps.get("Label", ""),
                    permission_type="permission_set",
                    description=ps.get("Description"),
                    object_permissions=obj_perms,
                )
            )
        logger.info("sf_permission_sets_pulled count=%d", len(results))
        return results
    except Exception as e:
        logger.warning("sf_permission_sets_failed error=%s", e)
        return []


def pull_profiles(sf: Salesforce) -> list[PermissionMeta]:
    try:
        raw = _rest_query_all(sf, "SELECT Id,Name FROM Profile")
        results = [
            PermissionMeta(
                api_name=p.get("Name", p.get("Id", "")),
                label=p.get("Name", ""),
                permission_type="profile",
                description=None,
                object_permissions=[],
            )
            for p in raw
        ]
        logger.info("sf_profiles_pulled count=%d", len(results))
        return results
    except Exception as e:
        logger.warning("sf_profiles_failed error=%s", e)
        return []


def pull_installed_packages(sf: Salesforce) -> list[dict]:
    try:
        raw = _tooling_query_all(
            sf,
            "SELECT Id,SubscriberPackage.Name,SubscriberPackage.NamespacePrefix,"
            "SubscriberPackageVersion.MajorVersion,SubscriberPackageVersion.MinorVersion,"
            "SubscriberPackageVersion.PatchVersion "
            "FROM InstalledSubscriberPackage",
        )
        results = []
        for pkg in raw:
            sp = pkg.get("SubscriberPackage") or {}
            spv = pkg.get("SubscriberPackageVersion") or {}
            version = f"{spv.get('MajorVersion', 0)}.{spv.get('MinorVersion', 0)}.{spv.get('PatchVersion', 0)}"
            results.append(
                {
                    "name": sp.get("Name", ""),
                    "namespace": sp.get("NamespacePrefix", ""),
                    "version": version,
                    "id": pkg.get("Id", ""),
                }
            )
        logger.info("sf_installed_packages_pulled count=%d", len(results))
        return results
    except Exception as e:
        logger.warning("sf_installed_packages_failed error=%s", e)
        return []


def pull_custom_metadata_types(sf: Salesforce, objects_list: list[dict]) -> list[dict]:
    """Pull Custom Metadata Type records for all __mdt objects in the org."""
    cmdt_objects = [
        o["name"] for o in objects_list
        if o.get("name", "").endswith("__mdt") and o.get("queryable")
    ]
    if not cmdt_objects:
        return []

    results = []
    for cmdt_name in cmdt_objects:
        if not _SAFE_CMDT_NAME.match(cmdt_name):
            logger.warning("cmdt_name_rejected name=%s", cmdt_name)
            continue
        try:
            result = sf.query_all(f"SELECT FIELDS(ALL) FROM {cmdt_name} LIMIT 200")
            records = result.get("records", [])
            field_names = []
            if records:
                field_names = [k for k in records[0].keys()
                               if k != "attributes" and not k.startswith("_")]
            results.append({
                "metadata_type": cmdt_name,
                "record_count": len(records),
                "records": records,
                "fields": field_names,
            })
        except Exception:
            logger.debug("cmdt_query_skipped type=%s", cmdt_name)
    logger.info("pull_custom_metadata_types count=%d", len(results))
    return results


def _composite_batch_count_queries(
    sf: Salesforce,
    queries: list[tuple[str, str]],
) -> dict[str, int]:
    """Run COUNT() SOQL queries via Composite Batch. Returns {obj_name: count}."""
    ver = sf.sf_version
    counts: dict[str, int] = {}
    batches = [
        queries[i : i + _COMPOSITE_BATCH_SIZE]
        for i in range(0, len(queries), _COMPOSITE_BATCH_SIZE)
    ]
    for batch in batches:
        subrequests = [
            {"method": "GET", "url": f"v{ver}/query?q={urllib.parse.quote(soql)}"}
            for _, soql in batch
        ]
        try:
            results = _composite_batch_post(sf, subrequests)
        except Exception as e:
            logger.warning("sf_count_batch_failed error=%s", e)
            for name, _ in batch:
                counts.setdefault(name, 0)
            continue
        for (name, _), sub in zip(batch, results):
            if sub.get("statusCode") == 200:
                counts[name] = sub.get("result", {}).get("totalSize", 0)
            else:
                counts.setdefault(name, 0)
    return counts


def pull_usage_data(
    sf: Salesforce,
    object_names: list[str],
    recency_days: int = 365,
    velocity_window_days: int = 30,
) -> UsageData:
    """Query record counts using /limits/recordCount + Composite Batch for recency/velocity."""
    total_counts: dict[str, int] = {}
    recent_counts: dict[str, int] = {}
    velocity_counts: dict[str, int] = {}

    try:
        joined = ",".join(object_names)
        resp = _sf_request_with_retry(sf.restful, f"limits/recordCount?sObjects={joined}")
        for entry in resp.get("sObjects", []):
            total_counts[entry["name"]] = entry.get("count", 0)
    except Exception as e:
        logger.warning("sf_record_count_failed error=%s — falling back to composite batch", e)
        fallback_queries = [(n, f"SELECT COUNT() FROM {n}") for n in object_names]
        total_counts = _composite_batch_count_queries(sf, fallback_queries)

    for name in object_names:
        total_counts.setdefault(name, 0)

    recency_queries = [
        (name, f"SELECT COUNT() FROM {name} WHERE LastModifiedDate >= LAST_N_DAYS:{recency_days}")
        for name in object_names
    ]
    recent_counts = _composite_batch_count_queries(sf, recency_queries)

    velocity_names = [n for n in object_names if total_counts.get(n, 0) > 0]
    if velocity_names:
        velocity_queries = [
            (name, f"SELECT COUNT() FROM {name} WHERE LastModifiedDate >= LAST_N_DAYS:{velocity_window_days}")
            for name in velocity_names
        ]
        velocity_counts = _composite_batch_count_queries(sf, velocity_queries)

    active_user_count = None
    try:
        result = _sf_request_with_retry(sf.query, "SELECT COUNT() FROM User WHERE IsActive = true")
        active_user_count = result.get("totalSize", 0)
    except Exception:
        pass

    logger.info(
        "sf_usage_data_complete objects=%d with_records=%d with_recent=%d",
        len(object_names),
        sum(1 for c in total_counts.values() if c > 0),
        sum(1 for c in recent_counts.values() if c > 0),
    )
    return UsageData(
        object_record_counts=total_counts,
        object_recent_counts=recent_counts,
        velocity_counts=velocity_counts,
        active_user_count=active_user_count,
    )


def pull_all_permissions(sf: Salesforce) -> list[PermissionMeta]:
    permissions: list[PermissionMeta] = []
    permissions.extend(pull_permission_sets(sf))
    permissions.extend(pull_profiles(sf))
    logger.info("sf_all_permissions_complete total=%d", len(permissions))
    return permissions


async def _mdapi_retrieve_files(sf: Salesforce) -> dict[str, bytes]:
    return await asyncio.to_thread(retrieve_metadata, sf)


def _collect_mdapi_zip_results(
    connection_id: UUID,
    org_id: UUID,
    files: dict[str, bytes],
    *,
    cached_metadata_by_key: dict[tuple[str, str, str], dict[str, Any]] | None = None,
    cached_workflow_bundles: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Parse MDAPI zip into pending ORM rows (not attached to a session)."""
    counts = {
        "flows": 0,
        "apex_classes": 0,
        "apex_triggers": 0,
        "objects": 0,
        "workflows": 0,
        "approvals": 0,
        "flexi": 0,
        "cache_hits": 0,
    }
    pending_automations: list[MetadataAutomation] = []
    pending_components: list[MetadataComponent] = []
    pending_objects_patch: dict[str, dict[str, Any]] = {}

    for path, raw in files.items():
        lower = path.lower()
        if lower.endswith(".flow-meta.xml"):
            dev_name = path.split("/")[-1].replace(".flow-meta.xml", "")
            file_hash = hashlib.sha256(raw).hexdigest()
            cache_key = (file_hash, "flow", dev_name)
            if cached_metadata_by_key and cache_key in cached_metadata_by_key:
                parsed = {**cached_metadata_by_key[cache_key]}
                counts["cache_hits"] += 1
            else:
                parsed = parse_flow(raw, path)
            status = parsed.get("status")
            parsed["active_matches_latest"] = status == "Active"
            pending_automations.append(
                MetadataAutomation(
                    connection_id=connection_id,
                    org_id=org_id,
                    automation_type="flow",
                    api_name=dev_name,
                    label=dev_name,
                    status=parsed.get("status"),
                    related_object=parsed.get("trigger_object"),
                    complexity_score=parsed.get("complexity_score"),
                    metadata_json=parsed,
                )
            )
            counts["flows"] += 1
        elif lower.endswith(".cls") and not lower.endswith("-meta.xml"):
            name = path.split("/")[-1].replace(".cls", "")
            meta_key = path.replace(".cls", ".cls-meta.xml")
            meta_xml = files.get(meta_key)
            file_hash = hashlib.sha256(raw).hexdigest()
            cls_key = (file_hash, "apex_class", name)
            if cached_metadata_by_key and cls_key in cached_metadata_by_key:
                analyzed = {**cached_metadata_by_key[cls_key]}
                counts["cache_hits"] += 1
            else:
                src = raw.decode("utf-8", errors="replace")
                analyzed = analyze_apex_class(src, meta_xml=meta_xml)
            pending_components.append(
                MetadataComponent(
                    org_id=org_id,
                    connection_id=connection_id,
                    component_category="apex_class",
                    api_name=name,
                    label=name,
                    status="Active",
                    metadata_json=analyzed,
                )
            )
            counts["apex_classes"] += 1
        elif lower.endswith(".trigger") and not lower.endswith("-meta.xml"):
            name = path.split("/")[-1].replace(".trigger", "")
            meta_key = path.replace(".trigger", ".trigger-meta.xml")
            meta_xml = files.get(meta_key)
            file_hash = hashlib.sha256(raw).hexdigest()
            tr_key = (file_hash, "trigger", name)
            if cached_metadata_by_key and tr_key in cached_metadata_by_key:
                analyzed = {**cached_metadata_by_key[tr_key]}
                counts["cache_hits"] += 1
            else:
                src = raw.decode("utf-8", errors="replace")
                analyzed = analyze_apex_trigger(src, meta_xml=meta_xml)
            pending_automations.append(
                MetadataAutomation(
                    connection_id=connection_id,
                    org_id=org_id,
                    automation_type="trigger",
                    api_name=name,
                    label=name,
                    status="Active",
                    related_object=analyzed.get("trigger_object"),
                    metadata_json=analyzed,
                )
            )
            counts["apex_triggers"] += 1
        elif lower.endswith(".object-meta.xml"):
            parsed = parse_custom_object(raw, path)
            api_name = path.split("/")[-1].replace(".object-meta.xml", "")
            pending_objects_patch[api_name] = parsed
            counts["objects"] += 1
            for bp in parsed.get("business_processes", []):
                bp_api_name = f"{api_name}.{bp['developer_name']}"
                pending_components.append(
                    MetadataComponent(
                        org_id=org_id,
                        connection_id=connection_id,
                        component_category="business_process",
                        api_name=bp_api_name,
                        label=bp["developer_name"],
                        related_object=api_name,
                        status="Active" if bp.get("active") else "Inactive",
                        metadata_json={
                            "description": bp.get("description"),
                            "related_object": api_name,
                            "is_active": bp.get("active"),
                            "values": bp.get("values", []),
                            "stage_count": len(bp.get("values", [])),
                        },
                    )
                )
                counts["business_processes"] = counts.get("business_processes", 0) + 1
        elif lower.endswith(".workflow-meta.xml"):
            file_hash = hashlib.sha256(raw).hexdigest()
            related_object = path.split("/")[-1].replace(".workflow-meta.xml", "")
            wb_key = (file_hash, related_object)
            if cached_workflow_bundles and wb_key in cached_workflow_bundles:
                counts["cache_hits"] += 1
                for row in cached_workflow_bundles[wb_key]:
                    row_c = {**row}
                    pending_automations.append(
                        MetadataAutomation(
                            connection_id=connection_id,
                            org_id=org_id,
                            automation_type="workflow_rule",
                            api_name=row_c.get("api_name") or "",
                            label=row_c.get("api_name"),
                            status="Active" if row_c.get("active") else "Inactive",
                            related_object=row_c.get("related_object"),
                            metadata_json=row_c,
                        )
                    )
                    counts["workflows"] += 1
            else:
                for row in parse_workflow(raw, path):
                    pending_automations.append(
                        MetadataAutomation(
                            connection_id=connection_id,
                            org_id=org_id,
                            automation_type="workflow_rule",
                            api_name=row.get("api_name") or "",
                            label=row.get("api_name"),
                            status="Active" if row.get("active") else "Inactive",
                            related_object=row.get("related_object"),
                            metadata_json=row,
                        )
                    )
                    counts["workflows"] += 1
        elif lower.endswith(".approvalprocess-meta.xml"):
            file_hash = hashlib.sha256(raw).hexdigest()
            dev_from_path = path.split("/")[-1].replace(".approvalprocess-meta.xml", "")
            ap_key = (file_hash, "approval_process", dev_from_path)
            if cached_metadata_by_key and ap_key in cached_metadata_by_key:
                parsed = {**cached_metadata_by_key[ap_key]}
                counts["cache_hits"] += 1
            else:
                parsed = parse_approval_process(raw, path)
            pending_automations.append(
                MetadataAutomation(
                    connection_id=connection_id,
                    org_id=org_id,
                    automation_type="approval_process",
                    api_name=parsed.get("api_name") or "",
                    label=parsed.get("api_name"),
                    status="Active" if parsed.get("active") else "Inactive",
                    related_object=parsed.get("related_object"),
                    metadata_json=parsed,
                )
            )
            counts["approvals"] += 1
        elif lower.endswith(".flexipage-meta.xml"):
            name = path.split("/")[-1].replace(".flexipage-meta.xml", "")
            file_hash = hashlib.sha256(raw).hexdigest()
            fp_key = (file_hash, "flexipage", name)
            if cached_metadata_by_key and fp_key in cached_metadata_by_key:
                flexi_meta = {**cached_metadata_by_key[fp_key]}
                flexi_meta["raw_xml_hash"] = file_hash
                flexi_meta["source_path"] = path
                counts["cache_hits"] += 1
            else:
                flexi_meta = {"raw_xml_hash": file_hash, "source_path": path}
            pending_components.append(
                MetadataComponent(
                    org_id=org_id,
                    connection_id=connection_id,
                    component_category="flexipage",
                    api_name=name,
                    label=name,
                    metadata_json=flexi_meta,
                )
            )
            counts["flexi"] += 1

    return {
        "counts": counts,
        "object_patches": pending_objects_patch,
        "pending_automations": pending_automations,
        "pending_components": pending_components,
    }


def _persist_mdapi_zip_results(
    connection_id: UUID,
    org_id: UUID,
    files: dict[str, bytes],
    db: AsyncSession,
    *,
    _precomputed: dict[str, Any] | None = None,
    cached_metadata_by_key: dict[tuple[str, str, str], dict[str, Any]] | None = None,
    cached_workflow_bundles: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Attach MDAPI-derived rows to the session (optionally using a pre-parsed bundle)."""
    payload = _precomputed or _collect_mdapi_zip_results(
        connection_id,
        org_id,
        files,
        cached_metadata_by_key=cached_metadata_by_key,
        cached_workflow_bundles=cached_workflow_bundles,
    )
    for auto in payload["pending_automations"]:
        db.add(auto)
    for comp in payload["pending_components"]:
        db.add(comp)
    return {"counts": payload["counts"], "object_patches": payload["object_patches"]}


async def sync_metadata(
    connection_id: UUID,
    db: AsyncSession,
    event_emitter: "SyncEventEmitter | None" = None,
) -> int:
    """Full metadata sync for a Salesforce connection.

    Pulls object describes, automations, usage counts, and related metadata; persists
    metadata objects, fields, and automations. Returns the number of objects synced.
    """

    async def _emit(
        event_type: str,
        message: str,
        *,
        phase: str | None = None,
        detail: dict | None = None,
        severity: str = "info",
    ) -> None:
        if event_emitter:
            try:
                await event_emitter.emit(event_type, message, phase=phase, detail=detail, severity=severity)
            except Exception:
                logger.exception(
                    "sync_event_emit_failed event_type=%s connection_phase=%s",
                    event_type,
                    phase,
                )

    stmt = select(PlatformConnection).where(PlatformConnection.id == connection_id)
    result = await db.execute(stmt)
    connection = result.scalar_one_or_none()
    if not connection or not connection.oauth_tokens_encrypted:
        logger.error("connection_not_found_or_no_tokens id=%s", connection_id)
        return 0

    org_id = connection.org_id
    tokens = json.loads(decrypt_tokens(connection.oauth_tokens_encrypted))
    sf = get_sf_client(tokens["instance_url"], tokens["access_token"])

    if not check_mdapi_access(sf):
        logger.error(
            "mdapi_access_denied connection_id=%s — connected user lacks Modify All Data permission",
            connection_id,
        )
        raise MDAPIInsufficientAccessError()

    connection.sync_config_json = {
        **connection.sync_config_json,
        "mdapi_capable": True,
        "last_mdapi_check": datetime.now(UTC).isoformat(),
    }

    await _emit("phase_start", "Pulling object describes...", phase="objects")
    await _emit("phase_start", "Retrieving metadata via MDAPI...", phase="mdapi_retrieve")

    objects, mdapi_files = await asyncio.gather(
        asyncio.to_thread(pull_object_describes, sf),
        _mdapi_retrieve_files(sf),
    )
    object_names = [o.api_name for o in objects]

    await _emit(
        "phase_complete",
        f"Object describes complete — {len(objects)} objects",
        phase="objects",
        detail={"count": len(objects)},
    )
    await _emit(
        "phase_complete",
        f"MDAPI retrieve complete — {len(mdapi_files)} files",
        phase="mdapi_retrieve",
        detail={"file_count": len(mdapi_files)},
    )

    org = await db.get(Organization, org_id)
    velocity_window_days = 30
    if org and org.analysis_config:
        velocity_window_days = org.analysis_config.get("velocity_window_days", 30)

    await _emit("item", f"Pulling usage data for {len(object_names)} objects...", phase="objects")
    usage = await asyncio.to_thread(
        pull_usage_data, sf, object_names, velocity_window_days=velocity_window_days,
    )
    for obj in objects:
        obj.record_count = usage.object_record_counts.get(obj.api_name, 0)
        obj.recent_record_count = usage.object_recent_counts.get(obj.api_name, 0)

    await _emit("phase_start", "Parsing MDAPI metadata...", phase="mdapi_parse")
    parse_cache_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    wf_groups: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    auto_cache_rows = await db.execute(
        select(
            MetadataAutomation.automation_type,
            MetadataAutomation.api_name,
            MetadataAutomation.related_object,
            MetadataAutomation.metadata_json,
        ).where(MetadataAutomation.connection_id == connection_id)
    )
    for at, api_name, rel_obj, mj in auto_cache_rows.all():
        if not mj or not isinstance(mj, dict):
            continue
        h = mj.get("raw_xml_hash")
        if not isinstance(h, str) or not h:
            continue
        if at == "workflow_rule" and rel_obj:
            wf_groups[(h, rel_obj)].append(mj)
        else:
            parse_cache_by_key[(h, str(at), api_name)] = mj
    parse_cache_workflows = {
        k: sorted(v, key=lambda d: d.get("api_name") or "") for k, v in wf_groups.items()
    }
    comp_cache_rows = await db.execute(
        select(
            MetadataComponent.component_category,
            MetadataComponent.api_name,
            MetadataComponent.metadata_json,
        ).where(MetadataComponent.connection_id == connection_id)
    )
    for cat, api_name, mj in comp_cache_rows.all():
        if not mj or not isinstance(mj, dict):
            continue
        h = mj.get("raw_xml_hash")
        if not isinstance(h, str) or not h:
            continue
        parse_cache_by_key[(h, str(cat), api_name)] = mj
    logger.info(
        "mdapi_parse_cache_loaded connection=%s triples=%d workflow_bundles=%d",
        connection_id,
        len(parse_cache_by_key),
        len(parse_cache_workflows),
    )

    mdapi_bundle: dict[str, Any] = _collect_mdapi_zip_results(
        connection_id,
        org_id,
        mdapi_files,
        cached_metadata_by_key=parse_cache_by_key or None,
        cached_workflow_bundles=parse_cache_workflows or None,
    )
    logger.info(
        "mdapi_parse_complete connection=%s cache_hits=%s",
        connection_id,
        mdapi_bundle["counts"].get("cache_hits", 0),
    )
    object_patches: dict[str, dict[str, Any]] = mdapi_bundle["object_patches"]

    await _emit("phase_start", "Processing automations...", phase="automations")
    all_validation_rules: list[dict] = []
    for obj_api_name, patch in mdapi_bundle["object_patches"].items():
        for vr in patch.get("validation_rules", []):
            all_validation_rules.append({**vr, "_related_object": obj_api_name})
    await _emit(
        "phase_complete",
        f"Automations complete — {len(mdapi_bundle['pending_automations']) + len(all_validation_rules)} items",
        phase="automations",
        detail={"count": len(mdapi_bundle["pending_automations"]) + len(all_validation_rules)},
    )

    await _emit("phase_start", "Processing permissions...", phase="permissions")
    await _emit("phase_start", "Processing UI components...", phase="ui_components")

    objects_list_raw = await asyncio.to_thread(pull_object_list, sf)
    permissions, packages, cmdts = await asyncio.gather(
        asyncio.to_thread(pull_all_permissions, sf),
        asyncio.to_thread(pull_installed_packages, sf),
        asyncio.to_thread(pull_custom_metadata_types, sf, objects_list_raw),
    )

    await _emit(
        "phase_complete",
        f"Permissions complete — {len(permissions)} items",
        phase="permissions",
        detail={"count": len(permissions)},
    )
    flexi_count = mdapi_bundle["counts"]["flexi"]
    await _emit(
        "phase_complete",
        f"UI components complete — {mdapi_bundle['counts']['flexi']} items",
        phase="ui_components",
        detail={"count": mdapi_bundle["counts"]["flexi"]},
    )

    mo_subq = select(MetadataObject.id).where(MetadataObject.connection_id == connection_id)

    await db.execute(delete(MetadataField).where(MetadataField.object_id.in_(mo_subq)))
    await db.execute(delete(MetadataAutomation).where(MetadataAutomation.connection_id == connection_id))
    await db.execute(delete(MetadataObject).where(MetadataObject.connection_id == connection_id))
    await db.execute(delete(MetadataComponent).where(MetadataComponent.connection_id == connection_id))
    await db.execute(delete(MetadataDependency).where(MetadataDependency.connection_id == connection_id))

    for obj in objects:
        metadata_json: dict[str, Any] = {
            "relationships": obj.relationships,
            "is_managed_package": obj.is_managed_package,
            "namespace_prefix": obj.namespace_prefix,
            "recent_record_count": obj.recent_record_count,
            "record_types": obj.record_types,
        }
        patch = object_patches.get(obj.api_name) if object_patches else None
        if patch:
            metadata_json = {**metadata_json, **patch}
        meta_obj = MetadataObject(
            connection_id=connection_id,
            org_id=org_id,
            api_name=obj.api_name,
            label=obj.label,
            object_type="Custom Object" if obj.is_custom else "Standard Object",
            field_count=obj.field_count,
            record_count=obj.record_count,
            is_custom=obj.is_custom,
            managed_package_namespace=obj.namespace_prefix,
            velocity_score=float(usage.velocity_counts.get(obj.api_name, 0)),
            metadata_json=metadata_json,
        )
        db.add(meta_obj)
        await db.flush()

        for fld in obj.fields:
            fname = fld["name"]
            db.add(
                MetadataField(
                    object_id=meta_obj.id,
                    api_name=fname,
                    label=fld.get("label", ""),
                    field_type=fld.get("type", ""),
                    is_custom=fname.endswith("__c"),
                    is_required=not fld.get("nillable", True),
                    metadata_json={
                        "description": fld.get("description", ""),
                        "picklist_values": fld.get("picklistValues", []),
                    },
                )
            )

    _persist_mdapi_zip_results(
        connection_id,
        org_id,
        mdapi_files,
        db,
        _precomputed=mdapi_bundle,
        cached_metadata_by_key=parse_cache_by_key,
        cached_workflow_bundles=parse_cache_workflows,
    )
    await db.flush()
    await _emit(
        "phase_complete",
        f"MDAPI parse complete — {sum(mdapi_bundle['counts'].values())} items",
        phase="mdapi_parse",
        detail=mdapi_bundle["counts"],
    )

    for vr in all_validation_rules:
        db.add(
            MetadataAutomation(
                connection_id=connection_id,
                org_id=org_id,
                api_name=vr.get("name", ""),
                label=vr.get("name", ""),
                automation_type="validation_rule",
                status="Active" if vr.get("active") else "Inactive",
                related_object=vr.get("_related_object"),
                metadata_json={
                    "description": vr.get("description"),
                    "error_condition_formula": vr.get("error_condition_formula"),
                    "error_message": vr.get("error_message"),
                    "error_display_field": vr.get("error_display_field"),
                    "is_active": vr.get("active", False),
                },
            )
        )

    await _emit("phase_start", "Processing code assets...", phase="code")
    apex_class_count = mdapi_bundle["counts"]["apex_classes"]
    await _emit(
        "phase_complete",
        f"Code assets complete — {apex_class_count} classes",
        phase="code",
        detail={"count": apex_class_count},
    )

    for perm in permissions:
        db.add(
            MetadataComponent(
                org_id=org_id,
                connection_id=connection_id,
                component_category=perm.permission_type,
                api_name=perm.api_name,
                label=perm.label,
                metadata_json={
                    "description": perm.description,
                    "object_permissions": perm.object_permissions,
                },
            )
        )

    await _emit("phase_start", "Processing installed packages...", phase="installed_packages")
    for pkg in packages:
        db.add(
            MetadataComponent(
                org_id=org_id,
                connection_id=connection_id,
                component_category="installed_package",
                api_name=pkg.get("namespace") or pkg.get("name", ""),
                label=pkg.get("name", ""),
                metadata_json={
                    "version": pkg.get("version", ""),
                    "namespace": pkg.get("namespace", ""),
                },
            )
        )
    await _emit(
        "phase_complete",
        f"Installed packages complete — {len(packages)} packages",
        phase="installed_packages",
        detail={"count": len(packages)},
    )

    await _emit("phase_start", "Processing custom metadata types...", phase="custom_metadata_types")
    for cmdt in cmdts:
        db.add(
            MetadataComponent(
                org_id=org_id,
                connection_id=connection_id,
                component_category="custom_metadata_type",
                api_name=cmdt["metadata_type"],
                label=cmdt["metadata_type"].replace("__mdt", "").replace("_", " "),
                metadata_json={
                    "record_count": cmdt["record_count"],
                    "fields": cmdt["fields"],
                    "records": cmdt["records"][:50],
                },
            )
        )
    await _emit(
        "phase_complete",
        f"Custom metadata types complete — {len(cmdts)} types",
        phase="custom_metadata_types",
        detail={"count": len(cmdts)},
    )

    await _emit("phase_start", "Capturing licensing snapshot...", phase="licensing")
    await _emit("phase_start", "Capturing user velocity...", phase="user_velocity")
    await _emit("phase_start", "Syncing org hierarchy...", phase="entities")

    from app.services.salesforce.licensing import (
        pull_org_info as _pull_lic_org_info,
        pull_user_licenses,
        pull_package_licenses,
        pull_permission_set_licenses,
        pull_limits,
        pull_experience_sites,
        estimate_annual_spend,
        COST_METHODOLOGY,
    )
    from app.services.salesforce.user_velocity import pull_user_velocity

    async def _fetch_licensing_data():
        return await asyncio.to_thread(
            lambda: {
                "org_info": _pull_lic_org_info(sf),
                "licenses": pull_user_licenses(sf),
                "pkg_licenses": pull_package_licenses(sf),
                "psl": pull_permission_set_licenses(sf),
                "limits": pull_limits(sf),
                "experience_sites": pull_experience_sites(sf),
            }
        )

    async def _fetch_velocity_data():
        return await asyncio.to_thread(pull_user_velocity, sf)

    lic_data, vel_data = None, None
    entity_count = 0
    lic_error, vel_error, ent_error = None, None, None

    async def _do_licensing():
        nonlocal lic_data, lic_error
        try:
            lic_data = await _fetch_licensing_data()
        except Exception as e:
            lic_error = e

    async def _do_velocity():
        nonlocal vel_data, vel_error
        try:
            vel_data = await _fetch_velocity_data()
        except Exception as e:
            vel_error = e

    async def _do_entities():
        nonlocal entity_count, ent_error
        try:
            from app.services.entities.profiler import sync_from_salesforce
            entity_count = await sync_from_salesforce(org_id, connection_id, db)
        except Exception as e:
            ent_error = e

    await asyncio.gather(_do_licensing(), _do_velocity(), _do_entities())

    if lic_error:
        logger.warning("licensing_snapshot_failed connection=%s error=%s", connection_id, lic_error)
        await _emit("warning", f"Licensing snapshot failed: {lic_error}", phase="licensing", severity="warning")
    elif lic_data:
        org_info_lic = lic_data["org_info"]
        edition = org_info_lic.get("OrganizationType", "")
        is_sandbox = bool(org_info_lic.get("IsSandbox", False))
        spend = estimate_annual_spend(edition, lic_data["licenses"])
        limits_ext = dict(lic_data["limits"])
        limits_ext["experience_sites"] = lic_data["experience_sites"]
        limits_ext["cost_methodology"] = COST_METHODOLOGY
        db.add(OrgLicenseSnapshot(
            org_id=org_id,
            connection_id=connection_id,
            edition=edition,
            is_sandbox=is_sandbox,
            licenses_json=lic_data["licenses"],
            package_licenses_json=lic_data["pkg_licenses"],
            psl_json=lic_data["psl"],
            limits_json=limits_ext,
            estimated_annual_spend=spend,
        ))
        await db.flush()
    await _emit("phase_complete", "Licensing snapshot complete", phase="licensing")

    if vel_error:
        logger.warning("user_velocity_snapshot_failed connection=%s error=%s", connection_id, vel_error)
        await _emit("warning", f"User velocity snapshot failed: {vel_error}", phase="user_velocity", severity="warning")
    elif vel_data:
        db.add(UserVelocitySnapshot(
            org_id=org_id,
            connection_id=connection_id,
            active_user_count=vel_data["active_user_count"],
            internal_active_count=vel_data["internal_active_count"],
            external_active_count=vel_data["external_active_count"],
            system_user_count=vel_data["system_user_count"],
            new_users_this_month=vel_data["new_users_this_month"],
            deactivated_this_month=vel_data["deactivated_this_month"],
            by_role_json=vel_data["by_role"],
            by_profile_json=vel_data["by_profile"],
            by_created_month_json=vel_data["by_created_month"],
        ))
        await db.flush()
    await _emit("phase_complete", "User velocity complete", phase="user_velocity")

    if ent_error:
        logger.warning("entity_sync_failed connection=%s error=%s", connection_id, ent_error)
        await _emit("warning", f"Entity sync failed: {ent_error}", phase="entities", severity="warning")
    await _emit(
        "phase_complete",
        f"Org hierarchy complete — {entity_count} entities",
        phase="entities",
        detail={"count": entity_count},
    )

    try:
        org = await db.get(Organization, org_id)
        if org is not None:
            if lic_data:
                org_info = lic_data["org_info"]
            else:
                from app.services.salesforce.licensing import pull_org_info as _pull_org_info
                org_info = _pull_org_info(sf)
            sf_org_name = org_info.get("Name", "")

            lic_stmt = select(OrgLicenseSnapshot).where(
                OrgLicenseSnapshot.org_id == org_id
            ).order_by(OrgLicenseSnapshot.snapshot_at.desc()).limit(1)
            lic_snap = (await db.execute(lic_stmt)).scalar_one_or_none()

            vel_stmt = select(UserVelocitySnapshot).where(
                UserVelocitySnapshot.org_id == org_id
            ).order_by(UserVelocitySnapshot.snapshot_at.desc()).limit(1)
            vel_snap = (await db.execute(vel_stmt)).scalar_one_or_none()

            pkg_rows = await db.execute(
                select(MetadataComponent.label).where(
                    MetadataComponent.org_id == org_id,
                    MetadataComponent.component_category == "installed_package",
                )
            )
            top_packages = [r[0] for r in pkg_rows.all() if r[0]]

            profile_count = 0
            role_count = 0
            if vel_snap:
                role_count = len(getattr(vel_snap, "by_role_json", {}) or {})
                profile_count = len(getattr(vel_snap, "by_profile_json", {}) or {})

            licenses_list = getattr(lic_snap, "licenses_json", []) or [] if lic_snap else []
            internal_lics = [
                license_item for license_item in licenses_list
                if license_item.get("category") == "internal"
            ]
            external_lics = [
                license_item for license_item in licenses_list
                if license_item.get("category") == "external"
            ]

            experience_sites = []
            if lic_snap:
                limits_data = getattr(lic_snap, "limits_json", {}) or {}
                experience_sites = limits_data.get("experience_sites", [])

            settings: dict[str, Any] = {
                "sf_org_name": sf_org_name,
                "sf_org_id": org_info.get("Id", ""),
                "edition": org_info.get("OrganizationType", ""),
                "is_sandbox": bool(org_info.get("IsSandbox", False)),
                "instance_name": org_info.get("InstanceName", ""),
                "instance_url": tokens.get("instance_url", ""),
                "active_users": getattr(vel_snap, "active_user_count", 0) if vel_snap else 0,
                "human_users": getattr(vel_snap, "internal_active_count", 0) if vel_snap else 0,
                "system_users": getattr(vel_snap, "system_user_count", 0) if vel_snap else 0,
                "external_users": getattr(vel_snap, "external_active_count", 0) if vel_snap else 0,
                "estimated_annual_spend": float(getattr(lic_snap, "estimated_annual_spend", 0) or 0) if lic_snap else 0,
                "top_packages": top_packages[:20],
                "license_summary": {
                    "total": sum(license_item.get("total", 0) for license_item in licenses_list),
                    "used": sum(license_item.get("used", 0) for license_item in licenses_list),
                    "internal_total": sum(license_item.get("total", 0) for license_item in internal_lics),
                    "internal_used": sum(license_item.get("used", 0) for license_item in internal_lics),
                    "external_total": sum(license_item.get("total", 0) for license_item in external_lics),
                    "external_used": sum(license_item.get("used", 0) for license_item in external_lics),
                },
                "role_count": role_count,
                "profile_count": profile_count,
                "experience_sites": experience_sites,
            }
            org.settings_json = settings

            if sf_org_name and (not org.name or org.name == org.clerk_org_id):
                org.name = sf_org_name
    except Exception as e:
        logger.warning("org_enrichment_failed connection=%s error=%s", connection_id, e)

    connection.last_sync_at = datetime.now(tz=UTC)
    connection.entity_count = len(objects)
    await db.commit()

    automation_count = len(mdapi_bundle["pending_automations"]) + len(all_validation_rules)
    logger.info(
        "sync_metadata_complete connection=%s objects=%d automations=%d permissions=%d ui=%d apex=%d packages=%d",
        connection_id,
        len(objects),
        automation_count,
        len(permissions),
        flexi_count,
        apex_class_count,
        len(packages),
    )
    return len(objects)


async def describe_global(connection: PlatformConnection) -> dict[str, Any]:
    """Return global describe for the connected org."""
    if not connection.oauth_tokens_encrypted:
        return {"sobjects": [], "connection_id": str(connection.id)}
    tokens = json.loads(decrypt_tokens(connection.oauth_tokens_encrypted))
    sf = get_sf_client(tokens["instance_url"], tokens["access_token"])
    return sf.describe()


async def describe_object(connection: PlatformConnection, object_name: str) -> dict[str, Any]:
    """Describe a single SObject including fields."""
    if not connection.oauth_tokens_encrypted:
        return {"name": object_name, "fields": [], "connection_id": str(connection.id)}
    tokens = json.loads(decrypt_tokens(connection.oauth_tokens_encrypted))
    sf = get_sf_client(tokens["instance_url"], tokens["access_token"])
    return getattr(sf, object_name).describe()
