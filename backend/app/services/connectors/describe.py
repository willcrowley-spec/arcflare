"""LLM-based object description generator for enriching metadata views.

Generates business-context descriptions of platform objects including
process roles, state fields, and key relationships.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.services.ai.router import llm_call, parse_json_response
from app.services.connectors.base import PlatformObjectMeta

logger = logging.getLogger(__name__)

_SYSTEM_FIELDS = {
    "Id", "IsDeleted", "CreatedDate", "CreatedById",
    "LastModifiedDate", "LastModifiedById", "SystemModstamp",
    "LastActivityDate", "LastViewedDate", "LastReferencedDate",
    "OwnerId", "RecordTypeId",
}

DESCRIBE_PROMPT = """Analyze this platform object metadata and write a brief structured analysis.

Object: {object_name}
Label: {label}
Record count: {record_count}

Fields (name -- type -- label):
{field_summary}

Relationships:
{relationship_summary}

Respond with ONLY a JSON object:
{{
    "description": "3-4 specific sentences about what business function this object serves.",
    "business_processes": ["List of business process names this object participates in"],
    "state_fields": [
        {{"field": "API field name", "stages": ["ordered values"], "represents": "what progression"}}
    ],
    "key_relationships": [
        {{"target_object": "API name", "relationship_type": "Lookup or MasterDetail", "business_meaning": "meaning"}}
    ],
    "process_role": "primary_process_object | supporting_object | reference_data | junction_object | system_object"
}}"""


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


def describe_object(obj: PlatformObjectMeta, model_config: dict | None = None) -> dict:
    """Generate AI description for a single platform object."""
    prompt = DESCRIBE_PROMPT.format(
        object_name=obj.api_name,
        label=obj.label,
        record_count=obj.record_count,
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


def describe_all_objects(
    objects: list[PlatformObjectMeta],
    max_workers: int = 4,
    model_config: dict | None = None,
) -> list[dict]:
    """Generate descriptions for all platform objects concurrently."""
    describable = [obj for obj in objects if obj.field_count > 3]
    logger.info("describing_objects count=%d", len(describable))

    descriptions: list[dict | None] = [None] * len(describable)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(describe_object, obj, model_config): i
            for i, obj in enumerate(describable)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                descriptions[idx] = future.result()
            except Exception as e:
                logger.warning("describe_failed object=%s error=%s", describable[idx].api_name, e)

    return [d for d in descriptions if d is not None]
