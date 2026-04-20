"""Evidence assembly, tagging, and resolution for discovery pipeline v2.

Phase 2 (assembly): graph traversal + vector search → focused evidence bundles.
Phase 4 (resolution): maps LLM-emitted tagged refs back to DB UUIDs for storage.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk
from app.models.metadata import (
    MetadataAutomation,
    MetadataComponent,
    MetadataDependency,
    MetadataField,
    MetadataObject,
)

logger = logging.getLogger(__name__)

MAX_FIELDS_PER_OBJECT = 25
MAX_EDGES = 150
MAX_DOC_CHUNKS_PER_DOMAIN = 8
MAX_BUNDLE_ITEMS = 40


@dataclass
class EvidenceItem:
    tag: str
    type: str
    id: str
    api_name: str = ""
    label: str = ""
    category: str = ""
    document_id: str = ""
    document_name: str = ""
    excerpt: str = ""
    content: str = ""


@dataclass
class EvidenceBundle:
    domain: dict
    items: list[EvidenceItem] = field(default_factory=list)
    dependency_edges: list[dict] = field(default_factory=list)
    community_summary: str | None = None

    def as_tagged_text(self) -> str:
        """Render the bundle as tagged text for the LLM prompt."""
        sections: list[str] = []

        objects = [i for i in self.items if i.type == "metadata_object"]
        automations = [i for i in self.items if i.type == "automation"]
        components = [i for i in self.items if i.type == "component"]
        doc_chunks = [i for i in self.items if i.type == "document_chunk"]

        if objects:
            lines = ["## Metadata Objects"]
            for item in objects:
                lines.append(f"[{item.tag}] {item.api_name} ({item.label})")
                if item.content:
                    lines.append(item.content)
            sections.append("\n".join(lines))

        if automations:
            lines = ["## Automations"]
            for item in automations:
                lines.append(f"[{item.tag}] {item.api_name} ({item.label})")
                if item.content:
                    lines.append(item.content)
            sections.append("\n".join(lines))

        if components:
            lines = ["## Components"]
            for item in components:
                lines.append(f"[{item.tag}] {item.api_name} ({item.label})")
                if item.content:
                    lines.append(item.content)
            sections.append("\n".join(lines))

        if doc_chunks:
            lines = ["## Document Passages"]
            for item in doc_chunks:
                lines.append(f"[{item.tag}] from \"{item.document_name}\"")
                lines.append(item.content)
            sections.append("\n".join(lines))

        if self.dependency_edges:
            edge_lines = ["## Dependency Edges"]
            for e in self.dependency_edges[:30]:
                edge_lines.append(
                    f"  {e['source']} ({e['source_type']}) "
                    f"—[{e['relationship']}]→ "
                    f"{e['target']} ({e['target_type']})"
                )
            sections.append("\n".join(edge_lines))

        if self.community_summary:
            sections.append(f"## Community Context\n{self.community_summary}")

        return "\n\n".join(sections)

    def tag_index(self) -> dict[str, EvidenceItem]:
        return {item.tag: item for item in self.items}


async def assemble_evidence_bundle(
    org_id: UUID,
    db: AsyncSession,
    domain: dict,
) -> EvidenceBundle:
    """Phase 2: assemble a focused evidence bundle for one domain.

    Uses graph traversal from key_objects through MetadataDependency,
    then loads object/automation/component details and runs vector
    search for document chunks.
    """
    bundle = EvidenceBundle(domain=domain)
    key_objects = domain.get("key_objects", [])
    key_terms = domain.get("key_terms", [])
    domain_name = domain.get("name", "")

    expanded_objects = set(key_objects)
    auto_names: set[str] = set()
    comp_names: set[str] = set()

    if key_objects:
        edges = await _expand_via_graph(org_id, db, key_objects)
        bundle.dependency_edges = edges
        _AUTO_TYPES = {"flow", "workflow_rule", "apex_trigger", "validation_rule", "approval_process"}
        _COMP_TYPES = {"apex_class", "business_process"}
        for e in edges:
            tt = e["target_type"]
            if tt == "object":
                expanded_objects.add(e["target"])
            elif tt in _AUTO_TYPES:
                auto_names.add(e["target"])
            elif tt in _COMP_TYPES:
                comp_names.add(e["target"])
            st = e["source_type"]
            if st == "object":
                expanded_objects.add(e["source"])
            elif st in _AUTO_TYPES:
                auto_names.add(e["source"])
            elif st in _COMP_TYPES:
                comp_names.add(e["source"])

    obj_idx = 0
    if expanded_objects:
        obj_idx = await _load_objects(org_id, db, list(expanded_objects), bundle)

    auto_idx = obj_idx
    if auto_names or key_objects:
        auto_idx = await _load_automations(org_id, db, auto_names, key_objects, bundle, start_idx=obj_idx)

    comp_idx = auto_idx
    if comp_names:
        comp_idx = await _load_components(org_id, db, comp_names, bundle, start_idx=auto_idx)

    queries = [f"{domain_name} business process"]
    if key_terms:
        queries.append(" ".join(key_terms[:5]))
    await _load_document_chunks(org_id, db, queries, bundle, start_idx=comp_idx)

    bundle.community_summary = await _load_community_summary(
        org_id, db, expanded_objects,
        auto_names=auto_names, comp_names=comp_names,
        domain_name=domain_name,
    )

    return bundle


async def _expand_via_graph(
    org_id: UUID,
    db: AsyncSession,
    seed_objects: list[str],
    max_hops: int = 2,
) -> list[dict]:
    """Expand seed objects through MetadataDependency edges (up to max_hops)."""
    visited_sources: set[str] = set()
    current_seeds = set(seed_objects)
    all_edges: list[dict] = []

    for _hop in range(max_hops):
        if not current_seeds:
            break
        q = await db.execute(
            select(MetadataDependency).where(
                MetadataDependency.org_id == org_id,
                sa.or_(
                    MetadataDependency.source_api_name.in_(current_seeds),
                    MetadataDependency.target_api_name.in_(current_seeds),
                ),
            ).limit(MAX_EDGES)
        )
        edges = q.scalars().all()
        next_seeds: set[str] = set()
        for e in edges:
            edge_dict = {
                "source": e.source_api_name,
                "source_type": e.source_type,
                "relationship": e.relationship_type,
                "target": e.target_api_name,
                "target_type": e.target_type,
            }
            if e.source_api_name not in visited_sources:
                all_edges.append(edge_dict)
            next_seeds.add(e.target_api_name)
            next_seeds.add(e.source_api_name)
        visited_sources.update(current_seeds)
        current_seeds = next_seeds - visited_sources

    return all_edges[:MAX_EDGES]


async def _load_objects(
    org_id: UUID,
    db: AsyncSession,
    object_names: list[str],
    bundle: EvidenceBundle,
) -> int:
    """Load MetadataObject details into the bundle with full operational context."""
    q = await db.execute(
        select(MetadataObject).where(
            MetadataObject.org_id == org_id,
            MetadataObject.api_name.in_(object_names),
        )
    )
    objects = q.scalars().all()

    obj_ids = [o.id for o in objects]
    fields_by_obj: dict[UUID, list] = {oid: [] for oid in obj_ids}
    if obj_ids:
        fq = await db.execute(
            select(MetadataField).where(
                MetadataField.object_id.in_(obj_ids),
            ).limit(MAX_FIELDS_PER_OBJECT * len(obj_ids))
        )
        for f in fq.scalars().all():
            bucket = fields_by_obj.get(f.object_id)
            if bucket is not None and len(bucket) < MAX_FIELDS_PER_OBJECT:
                bucket.append(f)

    idx = 0
    for o in objects:
        if idx >= MAX_BUNDLE_ITEMS:
            break
        fields = fields_by_obj.get(o.id, [])
        custom_fields = [f for f in fields if f.is_custom]
        required_fields = [f for f in fields if f.is_required]
        relationships = [f for f in fields if f.relationship_to]
        meta = o.metadata_json or {}

        content_lines = [
            f"  Type: {'Custom' if o.is_custom else 'Standard'} Object",
            f"  Records: {o.record_count or 0}",
            f"  Fields: {o.field_count or len(fields)} ({len(custom_fields)} custom, {len(required_fields)} required)",
        ]

        if o.managed_package_namespace:
            content_lines.append(f"  Package: {o.managed_package_namespace}")

        if relationships:
            rel_strs = [f"{f.api_name}→{f.relationship_to}" for f in relationships[:10]]
            content_lines.append(f"  Relationships: {', '.join(rel_strs)}")

        key_fields = sorted(fields, key=lambda f: (not f.is_required, not f.is_custom))[:15]
        if key_fields:
            field_strs = []
            for f in key_fields:
                parts = [f"{f.api_name} ({f.field_type})"]
                if f.is_required:
                    parts.append("required")
                if f.relationship_to:
                    parts.append(f"→{f.relationship_to}")
                field_strs.append(", ".join(parts))
            content_lines.append(f"  Key Fields: {'; '.join(field_strs)}")

        vrs = meta.get("validation_rules", [])
        if vrs:
            vr_strs = []
            for vr in vrs[:8]:
                status = "Active" if vr.get("active") else "Inactive"
                vr_strs.append(f"{vr.get('name', '?')} [{status}]: {vr.get('error_condition_formula', '?')[:120]}")
            content_lines.append(f"  Validation Rules ({len(vrs)}): {'; '.join(vr_strs)}")

        ffs = meta.get("formula_fields", [])
        if ffs:
            ff_strs = [f"{ff.get('api_name', '?')}={ff.get('formula', '?')[:80]}" for ff in ffs[:6]]
            content_lines.append(f"  Formula Fields ({len(ffs)}): {'; '.join(ff_strs)}")

        rts = meta.get("record_types", [])
        if rts:
            rt_strs = [rt.get("developer_name", "?") if isinstance(rt, dict) else str(rt) for rt in rts[:5]]
            content_lines.append(f"  Record Types: {', '.join(rt_strs)}")

        sm = meta.get("sharing_model")
        if sm:
            content_lines.append(f"  Sharing Model: {sm}")

        rels = meta.get("relationships", [])
        if rels:
            extended_rels = []
            for r in rels[:8]:
                targets = r.get("targets", [])
                rtype = r.get("relationship_type", "Lookup")
                if targets:
                    extended_rels.append(f"{r.get('field_name', '')}→{','.join(targets)} ({rtype})")
            if extended_rels:
                content_lines.append(f"  Object Relationships: {'; '.join(extended_rels)}")

        bundle.items.append(EvidenceItem(
            tag=f"OBJ-{idx}",
            type="metadata_object",
            id=str(o.id),
            api_name=o.api_name,
            label=o.label or o.api_name,
            content="\n".join(content_lines),
        ))
        idx += 1

    return idx


async def _load_automations(
    org_id: UUID,
    db: AsyncSession,
    auto_names: set[str],
    key_objects: list[str],
    bundle: EvidenceBundle,
    start_idx: int = 0,
) -> int:
    """Load automations into the bundle. Returns next index."""
    conditions = [MetadataAutomation.org_id == org_id]
    if auto_names and key_objects:
        conditions.append(sa.or_(
            MetadataAutomation.api_name.in_(auto_names),
            MetadataAutomation.related_object.in_(key_objects),
        ))
    elif auto_names:
        conditions.append(MetadataAutomation.api_name.in_(auto_names))
    elif key_objects:
        conditions.append(MetadataAutomation.related_object.in_(key_objects))
    else:
        return start_idx

    q = await db.execute(select(MetadataAutomation).where(*conditions).limit(MAX_BUNDLE_ITEMS))
    idx = start_idx
    for a in q.scalars().all():
        if idx >= MAX_BUNDLE_ITEMS:
            break
        meta = a.metadata_json or {}
        content_lines = [f"  Type: {a.automation_type}", f"  Status: {a.status or 'Unknown'}"]
        if a.related_object:
            content_lines.append(f"  Object: {a.related_object}")
        desc = meta.get("description", "")
        if desc:
            content_lines.append(f"  Description: {desc[:200]}")

        if a.automation_type == "flow":
            pt = meta.get("process_type")
            if pt:
                content_lines.append(f"  Process Type: {pt}")
            tt = meta.get("trigger_type")
            if tt:
                content_lines.append(f"  Trigger Type: {tt}")
            objs = meta.get("objects_touched", [])
            if objs:
                content_lines.append(f"  Objects Touched: {', '.join(str(o) for o in objs[:10])}")
            ec = meta.get("element_count")
            if ec is not None:
                content_lines.append(f"  Element Count: {ec}")
            cs = meta.get("complexity_score")
            if cs is not None:
                content_lines.append(f"  Complexity: {cs}")
            elems = meta.get("elements", {})
            for key in ("decisions", "record_creates", "record_updates", "record_lookups", "subflows", "action_calls"):
                items = elems.get(key, [])
                if items:
                    names = [str(i.get("name", "?")) for i in items if isinstance(i, dict)][:6]
                    if names:
                        content_lines.append(f"  {key}: {', '.join(names)}")
            variables = meta.get("variables", [])
            if variables:
                var_names = [str(v.get("name", "")) for v in variables if isinstance(v, dict)][:8]
                if var_names:
                    content_lines.append(f"  Variables: {', '.join(var_names)}")
            formulas = meta.get("formulas", [])
            if formulas:
                for f in formulas[:3]:
                    content_lines.append(f"  Formula: {f.get('name', '?')} = {f.get('expression', '?')[:80]}")

        elif a.automation_type == "workflow_rule":
            criteria = meta.get("criteria", {})
            if criteria.get("formula"):
                content_lines.append(f"  Criteria: {criteria['formula'][:120]}")
            if criteria.get("trigger_type"):
                content_lines.append(f"  Trigger: {criteria['trigger_type']}")
            actions = meta.get("actions", {})
            for atype in ("field_updates", "email_alerts", "outbound_messages", "tasks"):
                alist = actions.get(atype, [])
                if alist:
                    names = [str(ac.get("name", "?")) for ac in alist if isinstance(ac, dict)]
                    content_lines.append(f"  {atype}: {', '.join(names)}")

        elif a.automation_type == "approval_process":
            if meta.get("entry_criteria_formula"):
                content_lines.append(f"  Entry Criteria: {meta['entry_criteria_formula'][:120]}")
            steps = meta.get("steps", [])
            for step in steps[:4]:
                content_lines.append(f"  Step {step.get('number', '?')}: assignee={step.get('assignee_type', '?')}")
            fa = meta.get("final_approval_actions", [])
            if fa:
                content_lines.append(f"  Final Actions: {', '.join(ac.get('name', '?') for ac in fa)}")

        elif a.automation_type == "trigger":
            events = meta.get("trigger_events", [])
            if events:
                content_lines.append(f"  Events: {', '.join(str(e) for e in events)}")
            dml = meta.get("dml_objects", [])
            if dml:
                content_lines.append(f"  DML Objects: {', '.join(str(o) for o in dml[:8])}")
            soql = meta.get("soql_objects", [])
            if soql:
                content_lines.append(f"  SOQL Objects: {', '.join(str(o) for o in soql[:8])}")

        bundle.items.append(EvidenceItem(
            tag=f"AUTO-{idx - start_idx}",
            type="automation",
            id=str(a.id),
            api_name=a.api_name,
            label=a.label or a.api_name,
            content="\n".join(content_lines),
        ))
        idx += 1

    return idx


async def _load_components(
    org_id: UUID,
    db: AsyncSession,
    comp_names: set[str],
    bundle: EvidenceBundle,
    start_idx: int = 0,
) -> int:
    """Load components into the bundle. Returns next index."""
    if not comp_names:
        return start_idx

    q = await db.execute(
        select(MetadataComponent).where(
            MetadataComponent.org_id == org_id,
            MetadataComponent.api_name.in_(comp_names),
        ).limit(15)
    )
    idx = start_idx
    for c in q.scalars().all():
        if idx >= MAX_BUNDLE_ITEMS:
            break
        meta = c.metadata_json or {}
        content_lines = [f"  Category: {c.component_category}"]
        desc = meta.get("description", "")
        if desc:
            content_lines.append(f"  Description: {desc[:200]}")
        related = meta.get("related_objects", [])
        if related:
            content_lines.append(f"  Related Objects: {', '.join(str(o) for o in related[:8])}")
        api_version = meta.get("api_version")
        if api_version:
            content_lines.append(f"  API Version: {api_version}")

        bundle.items.append(EvidenceItem(
            tag=f"COMP-{idx - start_idx}",
            type="component",
            id=str(c.id),
            api_name=c.api_name,
            label=c.label or c.api_name,
            category=c.component_category or "",
            content="\n".join(content_lines),
        ))
        idx += 1

    return idx


async def _load_document_chunks(
    org_id: UUID,
    db: AsyncSession,
    queries: list[str],
    bundle: EvidenceBundle,
    start_idx: int = 0,
) -> int:
    """Vector-search for document chunks and add to bundle."""
    from app.services.processes.context import batch_semantic_search

    try:
        results = await batch_semantic_search(
            org_id, db, queries, limit=MAX_DOC_CHUNKS_PER_DOMAIN
        )
    except Exception as exc:
        logger.warning("evidence_doc_search_failed org_id=%s error=%s", org_id, exc)
        return start_idx

    doc_name_cache: dict[str, str] = {}
    seen_chunk_ids: set[str] = set()
    idx = start_idx
    doc_idx = 0

    for chunk_list in results:
        for chunk in chunk_list:
            chunk_id = chunk.get("chunk_id", "")
            if chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)

            doc_id = chunk.get("document_id", "")
            if doc_id not in doc_name_cache:
                doc_name_cache[doc_id] = await _get_document_name(db, doc_id)

            content = (chunk.get("content") or "")[:600]
            bundle.items.append(EvidenceItem(
                tag=f"DOC-{doc_idx}",
                type="document_chunk",
                id=chunk_id,
                document_id=doc_id,
                document_name=doc_name_cache[doc_id],
                content=content,
                excerpt=content[:200],
            ))
            doc_idx += 1
            idx += 1
            if doc_idx >= MAX_DOC_CHUNKS_PER_DOMAIN:
                return idx

    return idx


async def _get_document_name(db: AsyncSession, doc_id: str) -> str:
    try:
        doc = await db.get(Document, UUID(doc_id))
        return doc.filename if doc else "Unknown"
    except Exception:
        return "Unknown"


async def _load_community_summary(
    org_id: UUID,
    db: AsyncSession,
    object_names: set[str],
    auto_names: set[str] | None = None,
    comp_names: set[str] | None = None,
    domain_name: str = "",
) -> str | None:
    """Find the metadata community summaries most relevant to this domain.

    Primary: embedding-based cosine similarity on domain_name.
    Fallback: member-overlap matching all type prefixes.
    """
    from app.models.knowledge import Community

    if domain_name:
        try:
            from app.services.ai.router import get_embedding_provider
            from app.services.documents.vectorizer import _embed

            client = get_embedding_provider()
            query_emb = await _embed(client, domain_name)

            async with db.begin_nested():
                q = await db.execute(
                    select(Community).where(
                        Community.org_id == org_id,
                        Community.source == "metadata",
                        Community.summary_embedding.isnot(None),
                    )
                    .order_by(Community.summary_embedding.cosine_distance(query_emb))
                    .limit(3)
                )
                results = q.scalars().all()
                if results:
                    summaries = [c.summary for c in results if c.summary]
                    if summaries:
                        return "\n\n".join(summaries[:3])
        except Exception:
            logger.warning("embedding_community_lookup_failed org_id=%s", org_id, exc_info=True)

    if not object_names and not auto_names and not comp_names:
        return None

    typed_names: set[str] = set()
    for n in object_names:
        typed_names.add(f"object:{n}")
    for n in (auto_names or set()):
        typed_names.add(f"flow:{n}")
        typed_names.add(f"workflow_rule:{n}")
        typed_names.add(f"validation_rule:{n}")
        typed_names.add(f"apex_trigger:{n}")
        typed_names.add(f"approval_process:{n}")
    for n in (comp_names or set()):
        typed_names.add(f"apex_class:{n}")
        typed_names.add(f"business_process:{n}")

    try:
        async with db.begin_nested():
            q = await db.execute(
                select(Community).where(
                    Community.org_id == org_id,
                    Community.source == "metadata",
                    Community.summary.isnot(None),
                ).limit(50)
            )
            communities = q.scalars().all()
    except Exception:
        logger.warning("community_load_failed org_id=%s", org_id, exc_info=True)
        return None

    if not communities:
        return None

    best_overlap = 0
    best_summaries: list[str] = []
    for comm in communities:
        members = set(comm.member_concept_ids or [])
        overlap = len(members & typed_names)
        if overlap > best_overlap:
            best_overlap = overlap
            best_summaries = [comm.summary or ""]
        elif overlap == best_overlap and overlap > 0 and comm.summary:
            best_summaries.append(comm.summary)

    return "\n\n".join(best_summaries[:3]) if best_summaries else None


def resolve_evidence_refs(
    bundle: EvidenceBundle,
    evidence_refs: list[str],
    verifications: dict[str, str] | None = None,
) -> list[dict]:
    """Convert tagged refs (OBJ-1, AUTO-3, DOC-5) to stored evidence_sources entries.

    Drops refs that failed verification (verdict=UNSUPPORTED).
    """
    tag_idx = bundle.tag_index()
    sources: list[dict] = []

    for ref in evidence_refs:
        item = tag_idx.get(ref)
        if not item:
            continue

        confidence = 0.9
        if verifications:
            verdict = verifications.get(ref, "CONFIRMED")
            if verdict == "UNSUPPORTED":
                continue
            if verdict == "WEAK":
                confidence = 0.5

        entry: dict = {"type": item.type, "relevance": "", "confidence": confidence}

        if item.type == "metadata_object":
            entry.update({"id": item.id, "api_name": item.api_name, "label": item.label})
        elif item.type == "automation":
            entry.update({"id": item.id, "api_name": item.api_name, "label": item.label})
        elif item.type == "component":
            entry.update({"id": item.id, "api_name": item.api_name, "category": item.category})
        elif item.type == "document_chunk":
            entry.update({
                "chunk_id": item.id,
                "document_id": item.document_id,
                "document_name": item.document_name,
                "excerpt": item.excerpt[:200],
            })

        sources.append(entry)

    return sources


def build_verification_pairs(
    bundle: EvidenceBundle,
    extraction_result: dict,
) -> list[dict]:
    """Build claim-evidence pairs for the verification LLM call."""
    tag_idx = bundle.tag_index()
    pairs: list[dict] = []

    for proc in extraction_result.get("processes", []):
        proc_name = proc.get("name", "")

        for ref in proc.get("evidence_refs", []):
            item = tag_idx.get(ref)
            if not item:
                continue
            pairs.append({
                "process_name": proc_name,
                "claim": f"Process '{proc_name}': {proc.get('description', '')[:150]}",
                "evidence_ref": ref,
                "evidence_text": item.content[:300],
            })

        for child in proc.get("children", []):
            child_name = child.get("name", "")
            for ref in child.get("evidence_refs", []):
                item = tag_idx.get(ref)
                if not item:
                    continue
                pairs.append({
                    "process_name": proc_name,
                    "claim": f"Step '{child_name}': {child.get('description', '')[:150]}",
                    "evidence_ref": ref,
                    "evidence_text": item.content[:300],
                })

    return pairs


def apply_verification_results(
    extraction_result: dict,
    verifications: list[dict],
) -> tuple[dict, dict[str, str]]:
    """Apply verification verdicts to the extraction result.

    Returns (updated_extraction, ref_verdicts_map).
    Processes with >50% UNSUPPORTED evidence get needs_review=true.
    """
    ref_verdicts: dict[str, str] = {}
    for v in verifications:
        ref = v.get("evidence_ref", "")
        verdict = v.get("verdict", "CONFIRMED")
        if ref:
            ref_verdicts[ref] = verdict

    for proc in extraction_result.get("processes", []):
        refs = proc.get("evidence_refs", [])
        if refs:
            unsupported = sum(1 for r in refs if ref_verdicts.get(r) == "UNSUPPORTED")
            if unsupported > len(refs) / 2:
                proc["needs_review"] = True
                proc["confidence"] = min(proc.get("confidence", 0.5), 0.4)

        proc["evidence_refs"] = [
            r for r in refs if ref_verdicts.get(r) != "UNSUPPORTED"
        ]

        for child in proc.get("children", []):
            child_refs = child.get("evidence_refs", [])
            if child_refs:
                child_unsupported = sum(
                    1 for r in child_refs if ref_verdicts.get(r) == "UNSUPPORTED"
                )
                if child_unsupported > len(child_refs) / 2:
                    child["needs_review"] = True
                    child["confidence"] = min(child.get("confidence", 0.5), 0.4)
            child["evidence_refs"] = [
                r for r in child_refs if ref_verdicts.get(r) != "UNSUPPORTED"
            ]

    return extraction_result, ref_verdicts
