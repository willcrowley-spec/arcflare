"""LLM-based object description generator for enriching metadata views.

Generates business-context descriptions of platform objects including
process roles, state fields, and key relationships.
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.router import llm_call, parse_json_response
from app.services.connectors.base import PlatformObjectMeta
from app.services.prompts.resolver import resolve_prompt_blocks

logger = logging.getLogger(__name__)

_SYSTEM_FIELDS = {
    "Id", "IsDeleted", "CreatedDate", "CreatedById",
    "LastModifiedDate", "LastModifiedById", "SystemModstamp",
    "LastActivityDate", "LastViewedDate", "LastReferencedDate",
    "OwnerId", "RecordTypeId",
}

_FALLBACK_DESCRIBE_PROMPT = """Analyze this platform object metadata and write a brief structured analysis.

Object: {object_name}
Label: {label}
Record count: {record_count}

Fields (name -- type -- label):
{field_summary}

Relationships:
{relationship_summary}

Respond with ONLY a JSON object:
{
    "description": "3-4 specific sentences about what business function this object serves.",
    "business_processes": ["List of business process names this object participates in"],
    "state_fields": [
        {"field": "API field name", "stages": ["ordered values"], "represents": "what progression"}
    ],
    "key_relationships": [
        {"target_object": "API name", "relationship_type": "Lookup or MasterDetail", "business_meaning": "meaning"}
    ],
    "process_role": "primary_process_object | supporting_object | reference_data | junction_object | system_object"
}"""

_METADATA_DYNAMIC_BODY = """Object: {object_name}
Label: {label}
Record count: {record_count}

Fields (name -- type -- label):
{field_summary}

Relationships:
{relationship_summary}"""


def _substitute_prompt_vars(template: str, **kwargs: str) -> str:
    out = template
    for key, val in kwargs.items():
        out = out.replace("{" + key + "}", val)
    return out


async def get_describe_prompt(org_id: UUID | None, db: AsyncSession) -> str:
    """Load metadata_enrichment instructions + protocol from the store, or fall back."""
    blocks = await resolve_prompt_blocks("metadata_enrichment", org_id, db)
    instructions = (blocks.get("instructions") or "").strip()
    protocol = (blocks.get("protocol") or "").strip()
    if instructions and protocol:
        return f"{instructions}\n\n{_METADATA_DYNAMIC_BODY}\n\n{protocol}"
    return _FALLBACK_DESCRIBE_PROMPT


def build_field_summary(obj: PlatformObjectMeta) -> str:
    lines = []
    for f in obj.fields:
        if f.get("name", "") in _SYSTEM_FIELDS:
            continue
        line = f"{f.get('name', '')} -- {f.get('type', '')} -- {f.get('label', '')}"
        picklist_values = f.get("picklistValues", [])
        if picklist_values:
            active = [pv["value"] for pv in picklist_values if pv.get("active")]
            if active:
                line += f" [{', '.join(active[:8])}]"
        lines.append(line)
    return "\n".join(lines[:40])


def build_relationship_summary(obj: PlatformObjectMeta) -> str:
    if not obj.relationships:
        rels = []
        for f in obj.fields:
            if f.get("type") == "reference" and f.get("referenceTo"):
                targets = ", ".join(f["referenceTo"])
                rel_type = "MasterDetail" if not f.get("nillable", True) else "Lookup"
                rels.append(f"{f['name']} -> {targets} ({rel_type})")
        return "\n".join(rels) if rels else "None"

    lines = []
    for rel in obj.relationships:
        targets = ", ".join(rel.get("targets", []))
        lines.append(f"{rel.get('field_name', '')} -> {targets} ({rel.get('relationship_type', 'Lookup')})")
    return "\n".join(lines) if lines else "None"


def _describe_object_with_template(
    obj: PlatformObjectMeta,
    template: str,
    model_config: dict | None = None,
) -> dict:
    """Generate AI description for a single platform object (sync; for thread pool)."""
    prompt = _substitute_prompt_vars(
        template,
        object_name=obj.api_name,
        label=obj.label,
        record_count=str(obj.record_count),
        field_summary=build_field_summary(obj),
        relationship_summary=build_relationship_summary(obj),
    )

    result = llm_call(
        prompt=prompt, max_tokens=4000, tier="lite",
        operation="metadata_enrichment", model_config=model_config,
    )

    try:
        data = parse_json_response(result.text)
    except Exception:
        logger.warning("describe_parse_failed object=%s", obj.api_name)
        data = {"description": result.text[:500], "business_processes": [], "state_fields": [],
                "key_relationships": [], "process_role": "unknown"}

    data["object_name"] = obj.api_name
    data["object_label"] = obj.label
    data["record_count"] = obj.record_count
    data["token_usage"] = {"input": result.input_tokens, "output": result.output_tokens}
    return data


async def describe_object(
    obj: PlatformObjectMeta,
    model_config: dict | None = None,
    org_id: UUID | None = None,
    db: AsyncSession | None = None,
) -> dict:
    """Generate AI description for a single platform object."""
    if org_id is not None and db is not None:
        template = await get_describe_prompt(org_id, db)
    else:
        template = _FALLBACK_DESCRIBE_PROMPT
    return _describe_object_with_template(obj, template, model_config=model_config)


async def describe_all_objects(
    objects: list[PlatformObjectMeta],
    max_workers: int = 4,
    model_config: dict | None = None,
    org_id: UUID | None = None,
    db: AsyncSession | None = None,
) -> list[dict]:
    """Generate descriptions for all platform objects concurrently."""
    describable = [obj for obj in objects if obj.field_count > 3]
    logger.info("describing_objects count=%d", len(describable))

    if org_id is not None and db is not None:
        template = await get_describe_prompt(org_id, db)
    else:
        template = _FALLBACK_DESCRIBE_PROMPT

    loop = asyncio.get_running_loop()
    descriptions: list[dict | None] = [None] * len(describable)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        tasks = [
            loop.run_in_executor(
                executor,
                _describe_object_with_template,
                obj,
                template,
                model_config,
            )
            for obj in describable
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(
                "describe_failed object=%s error=%s",
                describable[i].api_name,
                result,
            )
        else:
            descriptions[i] = result

    return [d for d in descriptions if d is not None]
