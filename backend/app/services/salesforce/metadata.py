"""Salesforce metadata synchronization.

Pulls object describes, fields, flows, apex classes/triggers, validation rules,
workflow rules, approval processes, page layouts, flexipages, reports, dashboards,
profiles, and permission sets using the Metadata and Tooling APIs.
"""
import json
import logging
import urllib.parse
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from simple_salesforce import Salesforce
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_tokens
from app.models.connection import PlatformConnection
from app.models.licensing import OrgLicenseSnapshot, UserVelocitySnapshot
from app.models.metadata import MetadataAutomation, MetadataComponent, MetadataField, MetadataObject
from app.models.organization import Organization
from app.services.connectors.base import (
    AutomationMeta,
    PermissionMeta,
    PlatformObjectMeta,
    UIComponentMeta,
    UsageData,
)
from app.services.salesforce.licensing import snapshot_licensing
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
                )
            )
        except Exception as e:
            logger.warning("sf_describe_failed object=%s error=%s", obj_name, e)

    logger.info("sf_all_describes_complete count=%d", len(results))
    return results


def pull_flows(sf: Salesforce) -> list[AutomationMeta]:
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


def pull_apex_triggers(sf: Salesforce) -> list[AutomationMeta]:
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


def pull_apex_classes(sf: Salesforce) -> list[dict]:
    try:
        soql = (
            "SELECT Id,Name,ApiVersion,Status,LengthWithoutComments "
            "FROM ApexClass WHERE NamespacePrefix=null"
        )
        return _tooling_query_all(sf, soql)
    except Exception as e:
        logger.warning("sf_apex_classes_failed error=%s", e)
        return []


def pull_validation_rules(sf: Salesforce, object_name: str) -> list[dict]:
    try:
        soql = (
            f"SELECT Id,ValidationName,Active,Description,ErrorMessage "
            f"FROM ValidationRule "
            f"WHERE EntityDefinition.QualifiedApiName='{object_name}'"
        )
        return _tooling_query_all(sf, soql)
    except Exception as e:
        logger.warning("sf_validation_rules_failed object=%s error=%s", object_name, e)
        return []


def pull_objects_with_validation_rules(sf: Salesforce) -> set[str]:
    """Return SObject API names that have at least one unmanaged validation rule."""
    try:
        raw = _tooling_query_all(
            sf,
            "SELECT EntityDefinition.QualifiedApiName objName "
            "FROM ValidationRule WHERE NamespacePrefix = null",
        )
        names: set[str] = set()
        for r in raw:
            qn = r.get("objName") or (r.get("EntityDefinition") or {}).get("QualifiedApiName")
            if qn:
                names.add(qn)
        return names
    except Exception as e:
        logger.warning("sf_validation_rule_object_names_failed error=%s", e)
        return set()


def pull_workflow_rules(sf: Salesforce) -> list[AutomationMeta]:
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


def pull_approval_processes(sf: Salesforce) -> list[AutomationMeta]:
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


def pull_page_layouts(sf: Salesforce, object_names: list[str]) -> list[UIComponentMeta]:
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


def pull_flexipages(sf: Salesforce) -> list[UIComponentMeta]:
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


def pull_reports(sf: Salesforce) -> list[UIComponentMeta]:
    try:
        raw = _tooling_query_all(
            sf,
            "SELECT Id,Name,DeveloperName,Description,Format FROM Report WHERE NamespacePrefix=null",
        )
        return [
            UIComponentMeta(
                api_name=r.get("DeveloperName", r.get("Id", "")),
                label=r.get("Name", ""),
                component_type="report",
                description=r.get("Description"),
            )
            for r in raw
        ]
    except Exception as e:
        logger.warning("sf_reports_failed error=%s", e)
        return []


def pull_dashboards(sf: Salesforce) -> list[UIComponentMeta]:
    try:
        raw = _tooling_query_all(
            sf,
            "SELECT Id,Title,DeveloperName,Description FROM Dashboard WHERE NamespacePrefix=null",
        )
        return [
            UIComponentMeta(
                api_name=r.get("DeveloperName", r.get("Id", "")),
                label=r.get("Title", ""),
                component_type="dashboard",
                description=r.get("Description"),
            )
            for r in raw
        ]
    except Exception as e:
        logger.warning("sf_dashboards_failed error=%s", e)
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


def pull_usage_data(sf: Salesforce, object_names: list[str], recency_days: int = 365) -> UsageData:
    """Query record counts (total and recent) for each object."""
    total_counts: dict[str, int] = {}
    recent_counts: dict[str, int] = {}

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
        active_user_count=active_user_count,
    )


def pull_all_automations(sf: Salesforce) -> list[AutomationMeta]:
    automations: list[AutomationMeta] = []
    automations.extend(pull_flows(sf))
    automations.extend(pull_apex_triggers(sf))
    automations.extend(pull_workflow_rules(sf))
    automations.extend(pull_approval_processes(sf))
    logger.info("sf_all_automations_complete total=%d", len(automations))
    return automations


def pull_all_permissions(sf: Salesforce) -> list[PermissionMeta]:
    permissions: list[PermissionMeta] = []
    permissions.extend(pull_permission_sets(sf))
    permissions.extend(pull_profiles(sf))
    logger.info("sf_all_permissions_complete total=%d", len(permissions))
    return permissions


def pull_all_ui_components(sf: Salesforce, object_names: list[str]) -> list[UIComponentMeta]:
    components: list[UIComponentMeta] = []
    components.extend(pull_page_layouts(sf, object_names))
    components.extend(pull_flexipages(sf))
    components.extend(pull_reports(sf))
    components.extend(pull_dashboards(sf))
    logger.info("sf_all_ui_components_complete total=%d", len(components))
    return components


async def sync_metadata(
    connection_id: UUID,
    db: AsyncSession,
    progress_callback: callable | None = None,
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

    objects = pull_object_describes(sf)
    object_names = [o.api_name for o in objects]
    _progress("objects", "done", len(objects))

    usage = pull_usage_data(sf, object_names)
    for obj in objects:
        obj.record_count = usage.object_record_counts.get(obj.api_name, 0)
        obj.recent_record_count = usage.object_recent_counts.get(obj.api_name, 0)

    _progress("fields", "pulling", sum(o.field_count for o in objects))
    _progress("flows", "pulling", 0)
    _progress("triggers", "pulling", 0)
    _progress("validation_rules", "pulling", 0)

    automations = pull_all_automations(sf)
    flow_count = sum(1 for a in automations if a.automation_type in ("flow", "process_builder") and a.is_active)
    trigger_count = sum(1 for a in automations if a.automation_type == "trigger" and a.is_active)
    vr_count = sum(1 for a in automations if a.automation_type == "validation_rule" and a.is_active)
    _progress("flows", "done", flow_count)
    _progress("triggers", "done", trigger_count)
    _progress("validation_rules", "done", vr_count)

    _progress("permissions", "pulling", 0)
    permissions = pull_all_permissions(sf)
    _progress("permissions", "done", len(permissions))

    _progress("ui_components", "pulling", 0)
    _progress("reports", "pulling", 0)
    ui_components = pull_all_ui_components(sf, object_names)
    report_count = sum(1 for c in ui_components if c.component_type in ("report", "dashboard"))
    _progress("ui_components", "done", len(ui_components) - report_count)
    _progress("reports", "done", report_count)

    mo_subq = select(MetadataObject.id).where(MetadataObject.connection_id == connection_id)

    await db.execute(delete(MetadataField).where(MetadataField.object_id.in_(mo_subq)))
    await db.execute(delete(MetadataAutomation).where(MetadataAutomation.connection_id == connection_id))
    await db.execute(delete(MetadataObject).where(MetadataObject.connection_id == connection_id))
    await db.execute(delete(MetadataComponent).where(MetadataComponent.connection_id == connection_id))

    for obj in objects:
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
            metadata_json={
                "relationships": obj.relationships,
                "is_managed_package": obj.is_managed_package,
                "namespace_prefix": obj.namespace_prefix,
                "recent_record_count": obj.recent_record_count,
            },
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
                    metadata_json={"description": fld.get("description", "")},
                )
            )

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

    _progress("fields", "done", sum(o.field_count for o in objects))
    _progress("apex_classes", "pulling", 0)
    apex_classes = pull_apex_classes(sf)
    apex_classes = [ac for ac in apex_classes if ac.get("Status") != "Deleted"]
    for ac in apex_classes:
        db.add(
            MetadataComponent(
                org_id=org_id,
                connection_id=connection_id,
                component_category="apex_class",
                api_name=ac.get("Name", ac.get("Id", "")),
                label=ac.get("Name", ""),
                status=ac.get("Status", "Active"),
                metadata_json={
                    "api_version": ac.get("ApiVersion"),
                    "length_without_comments": ac.get("LengthWithoutComments"),
                },
            )
        )
    _progress("apex_classes", "done", len(apex_classes))

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

    auto_by_object: dict[str, dict[str, bool]] = {}
    for auto in automations:
        for rel in auto.related_objects:
            entry = auto_by_object.setdefault(
                rel, {"triggers": False, "flows": False, "validation_rules": False}
            )
            if auto.automation_type == "trigger":
                entry["triggers"] = True
            elif auto.automation_type in ("flow", "process_builder"):
                entry["flows"] = True

    vr_objects = pull_objects_with_validation_rules(sf)

    for obj_name, flags in auto_by_object.items():
        stmt = select(MetadataObject).where(
            MetadataObject.connection_id == connection_id,
            MetadataObject.api_name == obj_name,
        )
        res = await db.execute(stmt)
        mo = res.scalar_one_or_none()
        if mo:
            mo.has_triggers = flags.get("triggers", False)
            mo.has_flows = flags.get("flows", False)

    stmt_vr = select(MetadataObject).where(MetadataObject.connection_id == connection_id)
    res_vr = await db.execute(stmt_vr)
    for mo in res_vr.scalars().all():
        mo.has_validation_rules = mo.api_name in vr_objects

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

            settings: dict[str, Any] = {
                "sf_org_name": sf_org_name,
                "sf_org_id": org_info.get("Id", ""),
                "edition": org_info.get("OrganizationType", ""),
                "is_sandbox": bool(org_info.get("IsSandbox", False)),
                "instance_name": org_info.get("InstanceName", ""),
                "instance_url": tokens.get("instance_url", ""),
                "active_users": getattr(vel_snap, "active_user_count", 0) if vel_snap else 0,
                "estimated_annual_spend": float(getattr(lic_snap, "estimated_annual_spend", 0) or 0) if lic_snap else 0,
                "top_packages": top_packages[:20],
                "license_summary": {
                    "total": sum(l.get("total", 0) for l in (getattr(lic_snap, "licenses_json", []) or [])) if lic_snap else 0,
                    "used": sum(l.get("used", 0) for l in (getattr(lic_snap, "licenses_json", []) or [])) if lic_snap else 0,
                },
                "role_count": role_count,
                "profile_count": profile_count,
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
        len(apex_classes),
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
