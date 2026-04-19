"""NLP concept extraction following GraphRAG's SyntacticNounPhraseExtractor pattern."""

import hashlib
import json
import logging
import math
from itertools import combinations
from uuid import UUID

import spacy
from spacy.util import filter_spans
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.knowledge import Concept, ConceptCooccurrence

logger = logging.getLogger(__name__)

_nlp = None

STOPWORD_CONCEPTS = frozenset({
    "thing", "things", "way", "ways", "time", "times", "example",
    "part", "parts", "number", "lot", "kind", "type", "case",
    "point", "fact", "result", "end", "use",
})
MIN_CONCEPT_LEN = 2
MAX_CONCEPT_LEN = 100
MIN_COOCCURRENCE_FOR_PMI = 2


def _get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm", exclude=["lemmatizer"])
    return _nlp


def extract_noun_phrases(text_content: str) -> list[tuple[str, str]]:
    """Extract noun phrases from text. Returns list of (canonical_name, display_name)."""
    nlp = _get_nlp()
    doc = nlp(text_content[:100_000])

    ent_spans = list(doc.ents)
    chunk_spans = list(doc.noun_chunks)
    merged = filter_spans(ent_spans + chunk_spans)

    results: list[tuple[str, str]] = []
    for span in merged:
        display = span.text.strip()
        if len(display) < MIN_CONCEPT_LEN or len(display) > MAX_CONCEPT_LEN:
            continue
        if not any(t.pos_ in ("NOUN", "PROPN") for t in span):
            continue
        canonical = display.upper()
        if canonical.lower() in STOPWORD_CONCEPTS:
            continue
        results.append((canonical, display))

    return results


async def extract_and_store_concepts(
    chunks: list[dict],
    document_id: UUID,
    org_id: UUID,
    db: AsyncSession,
) -> int:
    """Extract concepts from chunks, build co-occurrence graph.

    Each chunk dict must have 'content' (str) and 'chunk_db_id' (UUID).
    Returns total concept count for the document.
    """
    all_chunk_concepts: list[list[tuple[str, str]]] = []
    doc_concept_set: set[str] = set()

    for chunk in chunks:
        content = chunk.get("content") or ""
        if not content.strip():
            all_chunk_concepts.append([])
            continue
        phrases = extract_noun_phrases(content)
        all_chunk_concepts.append(phrases)
        for canonical, _ in phrases:
            doc_concept_set.add(canonical)

    if not doc_concept_set:
        return 0

    concept_id_map: dict[str, UUID] = {}
    for canonical, display in {c: d for concepts in all_chunk_concepts for c, d in concepts}.items():
        stmt = pg_insert(Concept.__table__).values(
            org_id=org_id,
            name=canonical,
            display_name=display,
            concept_type="noun_phrase",
            frequency=1,
        ).on_conflict_do_update(
            constraint="uq_concepts_org_name",
            set_={"frequency": Concept.__table__.c.frequency + 1},
        ).returning(Concept.__table__.c.id)
        result = await db.execute(stmt)
        concept_id_map[canonical] = result.scalar_one()

    for i, chunk in enumerate(chunks):
        chunk_phrases = all_chunk_concepts[i]
        if not chunk_phrases:
            continue
        chunk_concept_ids = [str(concept_id_map[c]) for c, _ in chunk_phrases]

        chunk_db_id = chunk["chunk_db_id"]
        await db.execute(
            text("UPDATE document_chunks SET concept_ids = CAST(:ids AS jsonb), content_hash = :hash WHERE id = :cid"),
            {
                "ids": json.dumps(chunk_concept_ids),
                "hash": hashlib.sha256((chunk.get("content") or "").encode()).hexdigest(),
                "cid": str(chunk_db_id),
            },
        )

        canonical_names = list({c for c, _ in chunk_phrases})
        for a, b in combinations(sorted(canonical_names), 2):
            a_id, b_id = concept_id_map[a], concept_id_map[b]
            if a_id > b_id:
                a_id, b_id = b_id, a_id
            stmt = pg_insert(ConceptCooccurrence.__table__).values(
                org_id=org_id,
                concept_a_id=a_id,
                concept_b_id=b_id,
                raw_weight=1,
                document_ids=[str(document_id)],
            ).on_conflict_do_update(
                constraint="uq_cooccurrence_org_pair",
                set_={
                    "raw_weight": ConceptCooccurrence.__table__.c.raw_weight + 1,
                    "document_ids": text(
                        "concept_cooccurrences.document_ids || :new_doc_id::jsonb"
                    ),
                },
            )
            await db.execute(stmt, {"new_doc_id": f'["{document_id}"]'})

    await db.flush()
    return len(doc_concept_set)


async def compute_pmi_weights(org_id: UUID, db: AsyncSession) -> None:
    """Recompute PMI weights for all co-occurrence edges in an org."""
    total_q = await db.execute(
        select(Concept).where(Concept.org_id == org_id)
    )
    total_concepts = len(total_q.scalars().all())
    if total_concepts < 2:
        return

    total_chunks_q = await db.execute(text(
        "SELECT COUNT(*) FROM document_chunks dc "
        "JOIN documents d ON d.id = dc.document_id "
        "WHERE d.org_id = :org_id"
    ), {"org_id": str(org_id)})
    total_chunks = total_chunks_q.scalar() or 1

    edges_q = await db.execute(
        select(ConceptCooccurrence).where(ConceptCooccurrence.org_id == org_id)
    )
    edges = edges_q.scalars().all()

    concept_freq: dict[UUID, int] = {}
    concepts_q = await db.execute(
        select(Concept.id, Concept.frequency).where(Concept.org_id == org_id)
    )
    for cid, freq in concepts_q.all():
        concept_freq[cid] = freq

    for edge in edges:
        if edge.raw_weight < MIN_COOCCURRENCE_FOR_PMI:
            edge.pmi_weight = 0.0
            continue
        freq_a = concept_freq.get(edge.concept_a_id, 1)
        freq_b = concept_freq.get(edge.concept_b_id, 1)
        p_ab = edge.raw_weight / max(total_chunks, 1)
        p_a = freq_a / max(total_chunks, 1)
        p_b = freq_b / max(total_chunks, 1)
        if p_a * p_b > 0:
            edge.pmi_weight = max(0.0, math.log(p_ab / (p_a * p_b)))
        else:
            edge.pmi_weight = 0.0

    await db.flush()
