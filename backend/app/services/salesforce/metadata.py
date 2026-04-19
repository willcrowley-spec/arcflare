"""Salesforce metadata synchronization.

Pulls object describes, fields, flows, apex classes/triggers, validation rules,
workflow rules, approval processes, page layouts, flexipages, profiles, and permission
sets using the Metadata and Tooling APIs.
"""
import asyncio
import hashlib
import json
import logging
from collections import defaultdict
import re
import urllib.parse
from datetime import UTC, datetime
from collections.abc import Callable
from typing import Any
from uuid import UUID

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
    AutomationMeta,
    PermissionMeta,
    PlatformObjectMeta,
    UIComponentMeta,
    UsageData,
)
from app.services.salesforce.apex_parser.analyzer import analyze_apex_class, analyze_apex_trigger
from app.services.salesforce.licensing import snapshot_licensing
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
from app.services.salesforce.user_velocity import snapshot_user_velocity

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


def get_sf_client(instance_url: str, access_token: str) -> Salesforce:
    """Create a Salesforce client from stored credentials."""
    instance = instance_url.replace("https://", "").replace("http://", "")
    return Salesforce(instance=instance, session_id=access_token)


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


def pull_object_describes(sf: Salesforce, objects: list[str] | None = None) -> list[PlatformObjectMeta]:
    """Pull describes for all (or specified) objects."""
    if objects is None:
        all_objects = pull_object_list(sf)
        custom = [
            o["name"]
            for o in all_objects
            if o.get("name", "").endswith("__c") and o.get("queryable")
        ]
        objects = DEFAULT_OBJECTS + custom

    results: list[PlatformObjectMeta] = []
    for obj_name in objects:
        try:
            describe = getattr(sf, obj_name).describe()
            api_name = describe.get("name", "")
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
                if not rt.get("master", False)  # skip the Master record type
            ]

            results.append(
                PlatformObjectMeta(
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
            )
        except Exception as e:
            logger.warning("sf_describe_failed object=%s error=%s", obj_name, e)

    logger.info("sf_all_describes_complete count=%d", len(results))
    return results


def _legacy_pull_flows(sf: Salesforce) -> list[AutomationMeta]:
    try:
        raw = _tooling_query_all(sf, "SELECT Id,MasterLabel,ProcessType,Status,Description FROM Flow")
        results = []
        for flow in raw:
            pt = flow.get("ProcessType", "")
            auto_type = "process_builder" if pt in ("Workflow", "InvocableProcess") else "flow"
            results.append(
                AutomationMeta(
                    api_name=flow.get("Id", ""),
                    label=flow.get("MasterLabel", ""),
                    automation_type=auto_type,
                    is_active=flow.get("Status") == "Active",
                    description=flow.get("Description"),
                    related_objects=[],
                )
            )
        logger.info("sf_flows_pulled count=%d", len(results))
        return results
    except Exception as e:
        logger.warning("sf_flows_failed error=%s", e)
        return []


def _legacy_pull_apex_triggers(sf: Salesforce) -> list[AutomationMeta]:
    try:
        soql = (
            "SELECT Id,Name,ApiVersion,Status,"
            "EntityDefinition.QualifiedApiName,"
            "UsageBeforeInsert,UsageBeforeUpdate,UsageBeforeDelete,"
            "UsageAfterInsert,UsageAfterUpdate,UsageAfterDelete,UsageAfterUndelete "
            "FROM ApexTrigger WHERE NamespacePrefix=null"
        )
        raw = _tooling_query_all(sf, soql)
        results = []
        for trigger in raw:
            entity_def = trigger.get("EntityDefinition") or {}
            related_object = entity_def.get("QualifiedApiName", "")
            events = [
                k.replace("Usage", "")
                for k in [
                    "UsageBeforeInsert",
                    "UsageBeforeUpdate",
                    "UsageBeforeDelete",
                    "UsageAfterInsert",
                    "UsageAfterUpdate",
                    "UsageAfterDelete",
                    "UsageAfterUndelete",
                ]
                if trigger.get(k)
            ]
            results.append(
                AutomationMeta(
                    api_name=trigger.get("Name", ""),
                    label=trigger.get("Name", ""),
                    automation_type="trigger",
                    is_active=trigger.get("Status") == "Active",
                    description=f"Events: {', '.join(events)}" if events else None,
                    related_objects=[related_object] if related_object else [],
                )
            )
        logger.info("sf_apex_triggers_pulled count=%d", len(results))
        return results
    except Exception as e:
        logger.warning("sf_apex_triggers_failed error=%s", e)
        return []


def _legacy_pull_apex_classes(sf: Salesforce) -> list[dict]:
    try:
        soql = (
            "SELECT Id,Name,ApiVersion,Status,LengthWithoutComments "
            "FROM ApexClass WHERE NamespacePrefix=null"
        )
        return _tooling_query_all(sf, soql)
    except Exception as e:
        logger.warning("sf_apex_classes_failed error=%s", e)
        return []


def _legacy_pull_validation_rules_bulk(sf: Salesforce, object_names: list[str]) -> dict[str, list[dict]]:
    """Pull all validation rules in a single Tooling API query, grouped by object."""
    result_map: dict[str, list[dict]] = {name: [] for name in object_names}
    try:
        soql = (
            "SELECT Id,ValidationName,Active,Description,ErrorMessage,"
            "EntityDefinition.QualifiedApiName "
            "FROM ValidationRule"
        )
        rows = _tooling_query_all(sf, soql)
        for vr in rows:
            entity = (vr.get("EntityDefinition") or {}).get("QualifiedApiName", "")
            if entity in result_map:
                result_map[entity].append(vr)
        logger.info("sf_validation_rules_bulk count=%d", len(rows))
    except Exception as e:
        logger.warning("sf_validation_rules_bulk_failed error=%s", e)
    return result_map


def _legacy_pull_workflow_rules(sf: Salesforce) -> list[AutomationMeta]:
    try:
        raw = _tooling_query_all(sf, "SELECT Id,Name,TableEnumOrId FROM WorkflowRule")
        results = []
        for rule in raw:
            related_object = rule.get("TableEnumOrId", "")
            results.append(
                AutomationMeta(
                    api_name=rule.get("Name", rule.get("Id", "")),
                    label=rule.get("Name", ""),
                    automation_type="workflow_rule",
                    is_active=True,
                    related_objects=[related_object] if related_object else [],
                )
            )
        logger.info("sf_workflow_rules_pulled count=%d", len(results))
        return results
    except Exception as e:
        logger.warning("sf_workflow_rules_failed error=%s", e)
        return []


def _legacy_pull_approval_processes(sf: Salesforce) -> list[AutomationMeta]:
    try:
        result = sf.restful("process/approvals")
        approvals = result.get("approvals", {})
        results = []
        for name, details in approvals.items():
            items = details if isinstance(details, list) else [details] if isinstance(details, dict) else []
            for item in items:
                results.append(
                    AutomationMeta(
                        api_name=item.get("id", name),
                        label=item.get("name", name),
                        automation_type="approval_process",
                        is_active=True,
                        description=item.get("description"),
                        related_objects=[name] if name else [],
                    )
                )
        logger.info("sf_approval_processes_pulled count=%d", len(results))
        return results
    except Exception as e:
        logger.warning("sf_approval_processes_failed error=%s", e)
        return []


def _legacy_pull_business_processes(sf: Salesforce) -> list[dict]:
    """Pull BusinessProcess metadata (SalesProcess, SupportProcess, LeadProcess)."""
    try:
        raw = _tooling_query_all(
            sf,
            "SELECT Id,Name,TableEnumOrId,IsActive,Description FROM BusinessProcess",
        )
        results = []
        for bp in raw:
            results.append({
                "id": bp.get("Id", ""),
                "name": bp.get("Name", ""),
                "related_object": bp.get("TableEnumOrId", ""),
                "is_active": bp.get("IsActive", True),
                "description": bp.get("Description"),
            })
        logger.info("sf_business_processes_pulled count=%d", len(results))
        return results
    except Exception as e:
        logger.warning("sf_business_processes_failed error=%s", e)
        return []


def pull_permission_sets(sf: Salesforce) -> list[PermissionMeta]:
    try:
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
        for ps in raw:
            ps_id = ps.get("Id", "")
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
                    api_name=ps.get("Name", ""),
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


def _legacy_pull_page_layouts(sf: Salesforce, object_names: list[str]) -> list[UIComponentMeta]:
    results: list[UIComponentMeta] = []
    for obj_name in object_names:
        try:
            result = sf.restful(f"sobjects/{obj_name}/describe/layouts")
            for layout in result.get("layouts", []):
                results.append(
                    UIComponentMeta(
                        api_name=layout.get("id", ""),
                        label=layout.get("name", f"{obj_name} Layout"),
                        component_type="page_layout",
                        related_object=obj_name,
                    )
                )
        except Exception:
            continue
    logger.info("sf_page_layouts_pulled count=%d", len(results))
    return results


def _legacy_pull_flexipages(sf: Salesforce) -> list[UIComponentMeta]:
    try:
        raw = _tooling_query_all(
            sf,
            "SELECT Id,DeveloperName,MasterLabel,Description,Type FROM FlexiPage WHERE NamespacePrefix=null",
        )
        return [
            UIComponentMeta(
                api_name=r.get("DeveloperName", r.get("Id", "")),
                label=r.get("MasterLabel", ""),
                component_type="lightning_page",
                description=r.get("Description"),
            )
            for r in raw
        ]
    except Exception as e:
        logger.warning("sf_flexipages_failed error=%s", e)
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


def pull_usage_data(
    sf: Salesforce,
    object_names: list[str],
    recency_days: int = 365,
    velocity_window_days: int = 30,
) -> UsageData:
    """Query record counts (total and recent) for each object."""
    total_counts: dict[str, int] = {}
    recent_counts: dict[str, int] = {}
    velocity_counts: dict[str, int] = {}

    for obj_name in object_names:
        try:
            result = sf.query(f"SELECT COUNT() FROM {obj_name}")
            total_counts[obj_name] = result.get("totalSize", 0)
        except Exception:
            total_counts[obj_name] = 0

        try:
            result = sf.query(
                f"SELECT COUNT() FROM {obj_name} "
                f"WHERE LastModifiedDate >= LAST_N_DAYS:{recency_days}"
            )
            recent_counts[obj_name] = result.get("totalSize", 0)
        except Exception:
            recent_counts[obj_name] = 0

        if total_counts[obj_name] > 0:
            try:
                result = sf.query(
                    f"SELECT COUNT() FROM {obj_name} "
                    f"WHERE LastModifiedDate >= LAST_N_DAYS:{velocity_window_days}"
                )
                velocity_counts[obj_name] = result.get("totalSize", 0)
            except Exception:
                velocity_counts[obj_name] = 0

    active_user_count = None
    try:
        result = sf.query("SELECT COUNT() FROM User WHERE IsActive = true")
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


def _legacy_pull_all_automations(sf: Salesforce) -> list[AutomationMeta]:
    automations: list[AutomationMeta] = []
    automations.extend(_legacy_pull_flows(sf))
    automations.extend(_legacy_pull_apex_triggers(sf))
    automations.extend(_legacy_pull_workflow_rules(sf))
    automations.extend(_legacy_pull_approval_processes(sf))
    logger.info("sf_all_automations_complete total=%d", len(automations))
    return automations


def pull_all_permissions(sf: Salesforce) -> list[PermissionMeta]:
    permissions: list[PermissionMeta] = []
    permissions.extend(pull_permission_sets(sf))
    permissions.extend(pull_profiles(sf))
    logger.info("sf_all_permissions_complete total=%d", len(permissions))
    return permissions


def _legacy_pull_all_ui_components(sf: Salesforce, object_names: list[str]) -> list[UIComponentMeta]:
    components: list[UIComponentMeta] = []
    components.extend(_legacy_pull_page_layouts(sf, object_names))
    components.extend(_legacy_pull_flexipages(sf))
    logger.info("sf_all_ui_components_complete total=%d", len(components))
    return components


def _query_flow_definition_versions(sf: Salesforce) -> dict[str, dict[str, str | None]]:
    rows = _tooling_query_all(
        sf,
        "SELECT DeveloperName, ActiveVersionId, LatestVersionId FROM FlowDefinitionView",
    )
    out: dict[str, dict[str, str | None]] = {}
    for row in rows:
        name = row.get("DeveloperName") or ""
        out[name] = {
            "active_version_id": row.get("ActiveVersionId"),
            "latest_version_id": row.get("LatestVersionId"),
        }
    return out


async def _mdapi_retrieve_files(sf: Salesforce) -> dict[str, bytes]:
    return await asyncio.to_thread(retrieve_metadata, sf)


def _collect_mdapi_zip_results(
    connection_id: UUID,
    org_id: UUID,
    files: dict[str, bytes],
    flow_versions: dict[str, dict[str, str | None]],
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
            fv = flow_versions.get(dev_name, {})
            parsed["flow_definition_view"] = fv
            if fv.get("active_version_id") and fv.get("latest_version_id"):
                parsed["active_matches_latest"] = fv["active_version_id"] == fv["latest_version_id"]
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
    flow_versions: dict[str, dict[str, str | None]],
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
        flow_versions,
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
    progress_callback: Callable | None = None,
) -> int:
    """Full metadata sync for a Salesforce connection.

    Pulls object describes, automations, usage counts, and related metadata; persists
    metadata objects, fields, and automations. Returns the number of objects synced.
    """

    def _progress(phase: str, status: str, count: int = 0) -> None:
        if progress_callback:
            try:
                progress_callback(str(connection_id), phase, status, count)
            except Exception:
                pass

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

    objects = pull_object_describes(sf)
    object_names = [o.api_name for o in objects]
    _progress("objects", "done", len(objects))

    org = await db.get(Organization, org_id)
    velocity_window_days = 30
    if org and org.analysis_config:
        velocity_window_days = org.analysis_config.get("velocity_window_days", 30)

    usage = pull_usage_data(sf, object_names, velocity_window_days=velocity_window_days)
    for obj in objects:
        obj.record_count = usage.object_record_counts.get(obj.api_name, 0)
        obj.recent_record_count = usage.object_recent_counts.get(obj.api_name, 0)

    flow_versions: dict[str, dict[str, str | None]] = {}
    _progress("mdapi_retrieve", "pulling", 0)
    mdapi_files = await _mdapi_retrieve_files(sf)
    _progress("mdapi_retrieve", "done", len(mdapi_files))

    _progress("mdapi_parse", "pulling", 0)
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

    flow_versions = _query_flow_definition_versions(sf)
    mdapi_bundle: dict[str, Any] = _collect_mdapi_zip_results(
        connection_id,
        org_id,
        mdapi_files,
        flow_versions,
        cached_metadata_by_key=parse_cache_by_key or None,
        cached_workflow_bundles=parse_cache_workflows or None,
    )
    logger.info(
        "mdapi_parse_complete connection=%s cache_hits=%s",
        connection_id,
        mdapi_bundle["counts"].get("cache_hits", 0),
    )
    object_patches: dict[str, dict[str, Any]] = mdapi_bundle["object_patches"]

    _progress("automations", "pulling", 0)
    automations: list[AutomationMeta] = []
    # Extract VRs from MDAPI-parsed CustomObject data instead of Tooling API
    all_validation_rules: list[dict] = []
    for obj_api_name, patch in mdapi_bundle["object_patches"].items():
        for vr in patch.get("validation_rules", []):
            all_validation_rules.append({**vr, "_related_object": obj_api_name})
    _progress(
        "automations",
        "done",
        len(mdapi_bundle["pending_automations"]) + len(all_validation_rules),
    )

    _progress("permissions", "pulling", 0)
    permissions = pull_all_permissions(sf)
    _progress("permissions", "done", len(permissions))

    _progress("ui_components", "pulling", 0)
    ui_components: list[UIComponentMeta] = []
    _progress("ui_components", "done", mdapi_bundle["counts"]["flexi"])

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
        flow_versions,
        db,
        _precomputed=mdapi_bundle,
        cached_metadata_by_key=parse_cache_by_key,
        cached_workflow_bundles=parse_cache_workflows,
    )
    await db.flush()
    _progress("mdapi_parse", "done", sum(mdapi_bundle["counts"].values()))

    for auto in automations:
        if not auto.is_active:
            continue
        rel = auto.related_objects[0] if auto.related_objects else None
        db.add(
            MetadataAutomation(
                connection_id=connection_id,
                org_id=org_id,
                api_name=auto.api_name,
                label=auto.label,
                automation_type=auto.automation_type,
                status="Active" if auto.is_active else "Inactive",
                related_object=rel,
                metadata_json={
                    "description": auto.description,
                    "related_objects": auto.related_objects,
                    "is_active": auto.is_active,
                },
            )
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

    _progress("code", "pulling", 0)
    apex_class_count = mdapi_bundle["counts"]["apex_classes"]
    _progress("code", "done", apex_class_count)

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

    for comp in ui_components:
        db.add(
            MetadataComponent(
                org_id=org_id,
                connection_id=connection_id,
                component_category=comp.component_type,
                api_name=comp.api_name,
                label=comp.label,
                related_object=getattr(comp, "related_object", None),
                metadata_json={
                    "description": getattr(comp, "description", None),
                },
            )
        )

    _progress("installed_packages", "pulling", 0)
    packages = pull_installed_packages(sf)
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
    _progress("installed_packages", "done", len(packages))

    _progress("custom_metadata_types", "pulling", 0)
    objects_list_raw = pull_object_list(sf)
    cmdts = pull_custom_metadata_types(sf, objects_list_raw)
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
    _progress("custom_metadata_types", "done", len(cmdts))

    business_processes = _legacy_pull_business_processes(sf)
    for bp in business_processes:
        db.add(
            MetadataComponent(
                org_id=org_id,
                connection_id=connection_id,
                component_category="business_process",
                api_name=bp.get("name", bp.get("id", "")),
                label=bp.get("name", ""),
                related_object=bp.get("related_object"),
                status="Active" if bp.get("is_active") else "Inactive",
                metadata_json={
                    "description": bp.get("description"),
                    "related_object": bp.get("related_object"),
                    "is_active": bp.get("is_active"),
                },
            )
        )

    _progress("licensing", "pulling", 0)
    try:
        await snapshot_licensing(connection_id, org_id, sf, db)
    except Exception as e:
        logger.warning("licensing_snapshot_failed connection=%s error=%s", connection_id, e)
    _progress("licensing", "done", 1)

    _progress("user_velocity", "pulling", 0)
    try:
        await snapshot_user_velocity(connection_id, org_id, sf, db)
    except Exception as e:
        logger.warning("user_velocity_snapshot_failed connection=%s error=%s", connection_id, e)
    _progress("user_velocity", "done", 1)

    _progress("entities", "pulling", 0)
    try:
        from app.services.entities.profiler import sync_from_salesforce
        entity_count = await sync_from_salesforce(org_id, connection_id, db)
    except Exception as e:
        logger.warning("entity_sync_failed connection=%s error=%s", connection_id, e)
        entity_count = 0
    _progress("entities", "done", entity_count)

    try:
        org = await db.get(Organization, org_id)
        if org is not None:
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
            internal_lics = [l for l in licenses_list if l.get("category") == "internal"]
            external_lics = [l for l in licenses_list if l.get("category") == "external"]

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
                    "total": sum(l.get("total", 0) for l in licenses_list),
                    "used": sum(l.get("used", 0) for l in licenses_list),
                    "internal_total": sum(l.get("total", 0) for l in internal_lics),
                    "internal_used": sum(l.get("used", 0) for l in internal_lics),
                    "external_total": sum(l.get("total", 0) for l in external_lics),
                    "external_used": sum(l.get("used", 0) for l in external_lics),
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

    logger.info(
        "sync_metadata_complete connection=%s objects=%d automations=%d permissions=%d ui=%d apex=%d packages=%d",
        connection_id,
        len(objects),
        len(automations),
        len(permissions),
        len(ui_components),
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
