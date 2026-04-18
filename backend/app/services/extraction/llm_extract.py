"""LLM-based entity extraction for complex/ambiguous text.

Used as fallback when spaCy NER misses domain-specific entities.
"""
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.router import llm_call, parse_json_response
from app.services.extraction.ner import ExtractedEntity
from app.services.prompts.resolver import resolve_prompt_blocks

logger = logging.getLogger(__name__)

_FALLBACK_EXTRACTION_PROMPT = """Extract business entities from this text. Return ONLY a JSON array.

Each entity should have:
- "name": the entity name
- "type": one of "process", "metric", "product", "policy", "team", "system"
- "description": one sentence describing the entity in context

Only extract entities that are specific and meaningful. Skip generic terms.

Text:
{text}

JSON array:"""

_FALLBACK_BATCH_PROMPT = """Extract business entities from each text section. Return ONLY a JSON object mapping section numbers to arrays of entities.

Each entity: {"name": "...", "type": "process|metric|product|policy|team|system", "description": "..."}

{sections}

JSON object:"""


def _substitute_prompt_vars(template: str, **kwargs: str) -> str:
    out = template
    for key, val in kwargs.items():
        out = out.replace("{" + key + "}", val)
    return out


async def get_entity_extraction_prompt(org_id: UUID | None, db: AsyncSession) -> str:
    """Single-document entity_extraction: instructions + protocol, or fallback."""
    blocks = await resolve_prompt_blocks("entity_extraction", org_id, db)
    instructions = (blocks.get("instructions") or "").strip()
    protocol = (blocks.get("protocol") or "").strip()
    if instructions and protocol:
        return f"{instructions}\n\n{protocol}"
    return _FALLBACK_EXTRACTION_PROMPT


async def get_entity_extraction_batch_prompt(org_id: UUID | None, db: AsyncSession) -> str:
    """Batch entity_extraction: instructions_batch + protocol, or fallback."""
    blocks = await resolve_prompt_blocks("entity_extraction", org_id, db)
    batch = (blocks.get("instructions_batch") or "").strip()
    protocol = (blocks.get("protocol") or "").strip()
    if batch and protocol:
        return f"{batch}\n\n{protocol}"
    return _FALLBACK_BATCH_PROMPT


async def extract_with_llm(
    text: str,
    doc_id: str,
    model_config: dict | None = None,
    org_id: UUID | None = None,
    db: AsyncSession | None = None,
) -> list[ExtractedEntity]:
    """Use LLM to extract complex entities from a single text passage."""
    if org_id is not None and db is not None:
        template = await get_entity_extraction_prompt(org_id, db)
    else:
        template = _FALLBACK_EXTRACTION_PROMPT

    prompt = _substitute_prompt_vars(template, text=text[:3000])

    result = llm_call(
        prompt=prompt,
        max_tokens=1000,
        tier="fast",
        operation="entity_extraction",
        model_config=model_config,
    )

    try:
        entities_data = parse_json_response(result.text)
    except Exception:
        logger.warning("llm_extract_parse_failed doc=%s", doc_id)
        return []

    if not isinstance(entities_data, list):
        return []

    return [
        ExtractedEntity(
            name=e["name"],
            entity_type=e["type"],
            source_document_id=doc_id,
            confidence=0.8,
            description=e.get("description"),
            properties={"extraction_method": "llm"},
        )
        for e in entities_data
        if isinstance(e, dict) and "name" in e and "type" in e
    ]


async def extract_with_llm_batch(
    texts: list[str],
    doc_id: str,
    model_config: dict | None = None,
    org_id: UUID | None = None,
    db: AsyncSession | None = None,
) -> list[ExtractedEntity]:
    """Extract entities from multiple text chunks in a single API call."""
    all_entities: list[ExtractedEntity] = []

    if org_id is not None and db is not None:
        batch_template = await get_entity_extraction_batch_prompt(org_id, db)
    else:
        batch_template = _FALLBACK_BATCH_PROMPT

    for batch_start in range(0, len(texts), 10):
        batch = texts[batch_start:batch_start + 10]
        sections = "\n\n".join(f"--- Section {i} ---\n{t[:2000]}" for i, t in enumerate(batch))

        prompt = _substitute_prompt_vars(batch_template, sections=sections)

        result = llm_call(
            prompt=prompt, max_tokens=2000, tier="fast",
            operation="entity_extraction", model_config=model_config,
        )

        try:
            results = parse_json_response(result.text)
        except Exception:
            continue

        if not isinstance(results, dict):
            continue

        for section_idx, entities_data in results.items():
            if not isinstance(entities_data, list):
                continue
            for e in entities_data:
                if "name" in e and "type" in e:
                    all_entities.append(ExtractedEntity(
                        name=e["name"],
                        entity_type=e["type"],
                        source_document_id=doc_id,
                        confidence=0.8,
                        description=e.get("description"),
                        properties={"extraction_method": "llm_batch"},
                    ))

    return all_entities
