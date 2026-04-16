"""LLM-based entity extraction for complex/ambiguous text.

Used as fallback when spaCy NER misses domain-specific entities.
"""
import logging

from app.services.ai.router import llm_call, parse_json_response
from app.services.extraction.ner import ExtractedEntity

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Extract business entities from this text. Return ONLY a JSON array.

Each entity should have:
- "name": the entity name
- "type": one of "process", "metric", "product", "policy", "team", "system"
- "description": one sentence describing the entity in context

Only extract entities that are specific and meaningful. Skip generic terms.

Text:
{text}

JSON array:"""

BATCH_PROMPT = """Extract business entities from each text section. Return ONLY a JSON object mapping section numbers to arrays of entities.

Each entity: {{"name": "...", "type": "process|metric|product|policy|team|system", "description": "..."}}

{sections}

JSON object:"""


def extract_with_llm(text: str, doc_id: str) -> list[ExtractedEntity]:
    """Use LLM to extract complex entities from a single text passage."""
    result = llm_call(
        prompt=EXTRACTION_PROMPT.format(text=text[:3000]),
        max_tokens=1000,
        tier="fast",
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


def extract_with_llm_batch(texts: list[str], doc_id: str) -> list[ExtractedEntity]:
    """Extract entities from multiple text chunks in a single API call."""
    all_entities: list[ExtractedEntity] = []

    for batch_start in range(0, len(texts), 10):
        batch = texts[batch_start:batch_start + 10]
        sections = "\n\n".join(f"--- Section {i} ---\n{t[:2000]}" for i, t in enumerate(batch))

        result = llm_call(prompt=BATCH_PROMPT.format(sections=sections), max_tokens=2000, tier="fast")

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
