"""Named Entity Recognition using spaCy.

Extracts business entities (people, orgs, dates, metrics, products) from
parsed document elements using spaCy's NER pipeline with custom rules
for Salesforce IDs, emails, and KPI patterns.
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_nlp = None

LABEL_MAP = {
    "PERSON": "person",
    "ORG": "organization",
    "DATE": "date",
    "MONEY": "metric",
    "PRODUCT": "product",
    "GPE": "location",
    "SF_ID": "salesforce_id",
    "EMAIL": "email",
    "METRIC": "metric",
}


@dataclass
class ExtractedEntity:
    name: str
    entity_type: str
    source_document_id: str
    source_page: int | None = None
    confidence: float = 1.0
    description: str | None = None
    properties: dict | None = None


def _get_nlp():
    global _nlp
    if _nlp is not None:
        return _nlp

    try:
        import spacy
        _nlp = spacy.load("en_core_web_sm")
    except OSError:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_trf")
        except OSError:
            logger.warning("No spaCy model found. Install with: python -m spacy download en_core_web_sm")
            return None

    ruler = _nlp.add_pipe("entity_ruler", before="ner")
    patterns = [
        {"label": "SF_ID", "pattern": [{"TEXT": {"REGEX": r"^(001|003|006|00Q|500)[A-Za-z0-9]{12,15}$"}}]},
        {"label": "EMAIL", "pattern": [{"TEXT": {"REGEX": r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"}}]},
        {"label": "METRIC", "pattern": [
            {"TEXT": {"REGEX": r"^\$[\d,.]+[MBK]?$"}},
            {"LOWER": {"IN": ["revenue", "arr", "mrr", "sales", "cost"]}},
        ]},
    ]
    ruler.add_patterns(patterns)
    return _nlp


def extract_entities(doc_id: str, texts: list[tuple[str, int | None]]) -> list[ExtractedEntity]:
    """Run NER on text passages from a parsed document.

    Args:
        doc_id: Document ID for source tracking.
        texts: List of (text, page_number) tuples.

    Returns:
        Deduplicated list of extracted entities.
    """
    nlp = _get_nlp()
    if nlp is None:
        return []

    entities: list[ExtractedEntity] = []
    seen: set[str] = set()

    for text, page_num in texts:
        if not text or len(text.strip()) < 10:
            continue

        if len(text) > nlp.max_length:
            text = text[:nlp.max_length]

        doc = nlp(text)

        for ent in doc.ents:
            entity_type = LABEL_MAP.get(ent.label_)
            if entity_type is None:
                continue

            name = ent.text.strip()
            dedup_key = f"{entity_type}:{name.lower()}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            entities.append(ExtractedEntity(
                name=name,
                entity_type=entity_type,
                source_document_id=doc_id,
                source_page=page_num,
                confidence=1.0,
                properties={"spacy_label": ent.label_, "context": text[:200]},
            ))

    logger.info("ner_complete doc=%s entities=%d", doc_id, len(entities))
    return entities
