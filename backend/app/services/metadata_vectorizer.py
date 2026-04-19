"""Generate text representations of org metadata and vectorize for RAG."""
import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk
from app.models.licensing import OrgLicenseSnapshot
from app.models.metadata import (
    MetadataAutomation,
    MetadataComponent,
    MetadataField,
    MetadataObject,
)
from app.services.documents.vectorizer import vectorize_chunks

logger = logging.getLogger(__name__)

SYNTHETIC_MIME = "application/x-metadata-sync"


def _describe_object(obj: MetadataObject, fields: list[MetadataField]) -> str:
    lines = [
        f"Salesforce Object: {obj.label or obj.api_name} ({obj.api_name})",
        f"Type: {'Custom' if obj.is_custom else 'Standard'} Object",
        f"Record Count: {obj.record_count:,}",
        f"Field Count: {obj.field_count}",
    ]
    if obj.managed_package_namespace:
        lines.append(f"Managed Package: {obj.managed_package_namespace}")

    rels = (obj.metadata_json or {}).get("relationships", [])
    if rels:
        rel_strs = []
        for r in rels[:10]:
            targets = r.get("targets", [])
            rtype = r.get("relationship_type", "Lookup")
            if targets:
                rel_strs.append(f"{r.get('field_name', '')} -> {', '.join(targets)} ({rtype})")
        if rel_strs:
            lines.append("Relationships:")
            lines.extend(f"  - {s}" for s in rel_strs)

    if fields:
        custom_fields = [f for f in fields if f.is_custom]
        required_fields = [f for f in fields if f.is_required]
        lines.append(f"Custom Fields: {len(custom_fields)}")
        lines.append(f"Required Fields: {len(required_fields)}")

        key_fields = sorted(fields, key=lambda f: (not f.is_required, not f.is_custom))[:15]
        lines.append("Key Fields:")
        for f in key_fields:
            parts = [f"  - {f.label or f.api_name} ({f.api_name})"]
            parts.append(f"type={f.field_type}")
            if f.is_required:
                parts.append("required")
            if f.is_custom:
                parts.append("custom")
            if f.relationship_to:
                parts.append(f"-> {f.relationship_to}")
            lines.append(", ".join(parts))

    return "\n".join(lines)


def _describe_automation(auto: MetadataAutomation) -> str:
    lines = [
        f"Salesforce Automation: {auto.label or auto.api_name}",
        f"Type: {auto.automation_type}",
        f"Status: {auto.status or 'Unknown'}",
    ]
    if auto.related_object:
        lines.append(f"Related Object: {auto.related_object}")

    meta = auto.metadata_json or {}

    if meta.get("description"):
        lines.append(f"Description: {meta['description']}")

    if auto.automation_type == "flow":
        pt = meta.get("process_type")
        if pt:
            lines.append(f"Process Type: {pt}")
        tt = meta.get("trigger_type")
        if tt:
            lines.append(f"Trigger Type: {tt}")
        objs = meta.get("objects_touched", [])
        if objs:
            lines.append(f"Objects Touched: {', '.join(str(o) for o in objs)}")
        ec = meta.get("element_count")
        if ec is not None:
            lines.append(f"Element Count: {ec}")
        cs = meta.get("complexity_score")
        if cs is not None:
            lines.append(f"Complexity Score: {cs}")
        elems = meta.get("elements", {})
        for key in ("decisions", "record_creates", "record_updates", "record_lookups", "record_deletes", "subflows", "action_calls"):
            items = elems.get(key, [])
            if items:
                names = [str(i.get("name", "?")) for i in items if isinstance(i, dict)]
                if names:
                    lines.append(f"  {key}: {', '.join(names)}")
        variables = meta.get("variables", [])
        if variables:
            var_names = [str(v.get("name", "")) for v in variables if isinstance(v, dict)]
            if var_names:
                lines.append(f"Variables: {', '.join(var_names[:10])}")
        formulas = meta.get("formulas", [])
        if formulas:
            for f in formulas[:5]:
                lines.append(f"  Formula: {f.get('name', '?')} = {f.get('expression', '?')}")

    elif auto.automation_type == "workflow_rule":
        criteria = meta.get("criteria", {})
        if criteria.get("formula"):
            lines.append(f"Criteria Formula: {criteria['formula']}")
        if criteria.get("trigger_type"):
            lines.append(f"Trigger: {criteria['trigger_type']}")
        actions = meta.get("actions", {})
        for atype in ("field_updates", "email_alerts", "outbound_messages", "tasks"):
            alist = actions.get(atype, [])
            if alist:
                names = [str(a.get("name", "?")) for a in alist if isinstance(a, dict)]
                lines.append(f"  {atype}: {', '.join(names)}")

    elif auto.automation_type == "approval_process":
        if meta.get("entry_criteria_formula"):
            lines.append(f"Entry Criteria: {meta['entry_criteria_formula']}")
        steps = meta.get("steps", [])
        for step in steps:
            lines.append(f"  Step {step.get('number', '?')}: assignee={step.get('assignee_type', '?')}")
        fa = meta.get("final_approval_actions", [])
        if fa:
            lines.append(f"  Final Approval: {', '.join(a.get('name', '?') for a in fa)}")

    elif auto.automation_type == "trigger":
        events = meta.get("trigger_events", [])
        if events:
            lines.append(f"Events: {', '.join(str(e) for e in events)}")
        dml = meta.get("dml_objects", [])
        if dml:
            lines.append(f"DML Objects: {', '.join(str(o) for o in dml)}")
        soql = meta.get("soql_objects", [])
        if soql:
            lines.append(f"SOQL Objects: {', '.join(str(o) for o in soql)}")

    else:
        related = meta.get("related_objects", [])
        if related:
            lines.append(f"Objects: {', '.join(str(o) for o in related)}")

    return "\n".join(lines)


def _describe_component(comp: MetadataComponent) -> str:
    cat_labels = {
        "apex_class": "Apex Class",
        "permission_set": "Permission Set",
        "profile": "Profile",
        "page_layout": "Page Layout",
        "lightning_page": "Lightning Page",
        "report": "Report",
        "dashboard": "Dashboard",
        "installed_package": "Installed Package",
    }
    type_label = cat_labels.get(comp.component_category, comp.component_category)
    lines = [
        f"Salesforce {type_label}: {comp.label or comp.api_name}",
        f"API Name: {comp.api_name}",
    ]
    if comp.status:
        lines.append(f"Status: {comp.status}")
    if comp.related_object:
        lines.append(f"Related Object: {comp.related_object}")

    meta = comp.metadata_json or {}
    if comp.component_category == "apex_class":
        if meta.get("api_version"):
            lines.append(f"API Version: {meta['api_version']}")
        if meta.get("length_without_comments"):
            lines.append(f"Lines of Code: {meta['length_without_comments']}")
    elif comp.component_category in ("permission_set",):
        perms = meta.get("object_permissions", [])
        if perms:
            lines.append(f"Object Permissions: {len(perms)} objects")
            for p in perms[:5]:
                access = []
                if p.get("read"):
                    access.append("R")
                if p.get("create"):
                    access.append("C")
                if p.get("edit"):
                    access.append("U")
                if p.get("delete"):
                    access.append("D")
                lines.append(f"  - {p.get('object', '?')}: {''.join(access)}")
    elif comp.component_category == "installed_package":
        if meta.get("namespace"):
            lines.append(f"Namespace: {meta['namespace']}")
        if meta.get("version"):
            lines.append(f"Version: {meta['version']}")
    if meta.get("description"):
        lines.append(f"Description: {meta['description']}")
    return "\n".join(lines)


def _describe_licensing(snap: OrgLicenseSnapshot) -> str:
    lines = [
        f"Salesforce Org Licensing Snapshot",
        f"Edition: {snap.edition or 'Unknown'}",
        f"Sandbox: {'Yes' if snap.is_sandbox else 'No'}",
    ]
    if snap.estimated_annual_spend:
        lines.append(f"Estimated Annual Spend: ${snap.estimated_annual_spend:,.0f}")

    licenses = snap.licenses_json or []
    if licenses:
        lines.append(f"User Licenses ({len(licenses)} types):")
        for lic in licenses:
            total = lic.get("total", 0)
            used = lic.get("used", 0)
            pct = f" ({used/total*100:.0f}%)" if total else ""
            lines.append(f"  - {lic.get('type', '?')}: {used}/{total}{pct}")

    pkgs = snap.package_licenses_json or []
    if pkgs:
        lines.append(f"Package Licenses ({len(pkgs)}):")
        for p in pkgs:
            lines.append(f"  - {p.get('namespace', '?')}: {p.get('used', 0)}/{p.get('total', 0)}")

    limits = snap.limits_json or {}
    if limits:
        key_limits = ["DailyApiRequests", "DataStorageMB", "FileStorageMB", "DailyBulkApiRequests"]
        for k in key_limits:
            if k in limits:
                val = limits[k]
                if isinstance(val, dict):
                    lines.append(f"  {k}: {val.get('Remaining', '?')}/{val.get('Max', '?')} remaining")
    return "\n".join(lines)


async def vectorize_org_metadata(
    connection_id: UUID,
    org_id: UUID,
    db: AsyncSession,
) -> int:
    existing = await db.execute(
        select(Document).where(
            Document.org_id == org_id,
            Document.mime_type == SYNTHETIC_MIME,
            Document.tags.contains([str(connection_id)]),
        )
    )
    old_doc = existing.scalar_one_or_none()
    if old_doc:
        await db.execute(
            DocumentChunk.__table__.delete().where(DocumentChunk.document_id == old_doc.id)
        )
        await db.delete(old_doc)
        await db.flush()

    chunks: list[dict] = []
    idx = 0

    objects = (
        await db.execute(
            select(MetadataObject).where(
                MetadataObject.connection_id == connection_id,
                MetadataObject.record_count > 0,
                sa.or_(
                    MetadataObject.classification.is_(None),
                    MetadataObject.classification.notin_(["empty", "deprecated"]),
                ),
            )
        )
    ).scalars().all()

    for obj in objects:
        fields = (
            await db.execute(select(MetadataField).where(MetadataField.object_id == obj.id))
        ).scalars().all()
        text = _describe_object(obj, fields)
        chunks.append({
            "chunk_index": idx,
            "content": text,
            "section_title": f"Object: {obj.api_name}",
            "metadata_json": {"source": "metadata_sync", "type": "object", "api_name": obj.api_name},
        })
        idx += 1

    automations = (
        await db.execute(
            select(MetadataAutomation).where(MetadataAutomation.connection_id == connection_id)
        )
    ).scalars().all()

    for auto in automations:
        text = _describe_automation(auto)
        chunks.append({
            "chunk_index": idx,
            "content": text,
            "section_title": f"Automation: {auto.label or auto.api_name}",
            "metadata_json": {"source": "metadata_sync", "type": "automation", "api_name": auto.api_name},
        })
        idx += 1

    components = (
        await db.execute(
            select(MetadataComponent).where(MetadataComponent.connection_id == connection_id)
        )
    ).scalars().all()

    for comp in components:
        text = _describe_component(comp)
        chunks.append({
            "chunk_index": idx,
            "content": text,
            "section_title": f"{comp.component_category}: {comp.label or comp.api_name}",
            "metadata_json": {
                "source": "metadata_sync",
                "type": comp.component_category,
                "api_name": comp.api_name,
            },
        })
        idx += 1

    license_snap = (
        await db.execute(
            select(OrgLicenseSnapshot)
            .where(OrgLicenseSnapshot.connection_id == connection_id)
            .order_by(OrgLicenseSnapshot.snapshot_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if license_snap:
        text = _describe_licensing(license_snap)
        chunks.append({
            "chunk_index": idx,
            "content": text,
            "section_title": "Licensing Snapshot",
            "metadata_json": {"source": "metadata_sync", "type": "licensing"},
        })
        idx += 1

    if not chunks:
        return 0

    doc = Document(
        org_id=org_id,
        filename=f"metadata-sync-{connection_id}.txt",
        mime_type=SYNTHETIC_MIME,
        status="indexed",
        tags=[str(connection_id)],
        chunk_count=len(chunks),
    )
    db.add(doc)
    await db.flush()

    await vectorize_chunks(chunks, doc.id, db)
    await db.commit()

    logger.info(
        "vectorize_org_metadata_complete connection=%s chunks=%d",
        connection_id,
        len(chunks),
    )
    return len(chunks)
