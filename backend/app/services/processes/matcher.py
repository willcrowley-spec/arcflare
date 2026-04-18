"""Entity matching via fuzzy string matching + cosine similarity + LLM disambiguation.

Connects entities across documents and data sources by finding
similar or identical entities using a multi-stage approach:
1. Exact name match -> SAME_AS relationship
2. Fuzzy match (rapidfuzz) -> candidate pairs
3. Cosine similarity on embeddings -> score pairs
4. LLM disambiguation for ambiguous cases -> confirm/reject
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    entity_a_id: str
    entity_b_id: str
    entity_a_name: str
    entity_b_name: str
    match_type: str  # "exact", "fuzzy", "semantic", "llm_confirmed"
    score: float
    relationship: str  # "SAME_AS" or "RELATED_TO"


def find_matches(
    entities: list[dict],
    fuzzy_threshold: float = 80.0,
    cosine_threshold: float = 0.75,
    use_llm: bool = True,
    model_config: dict | None = None,
) -> list[MatchResult]:
    """Find matching entities across a set of entities.

    Args:
        entities: List of dicts with 'id', 'name', 'entity_type', 'embedding' (optional).
        fuzzy_threshold: Minimum rapidfuzz score to consider a match (0-100).
        cosine_threshold: Minimum cosine similarity for embedding-based matches.
        use_llm: Whether to use LLM for ambiguous pair disambiguation.

    Returns:
        List of MatchResult objects describing discovered relationships.
    """
    matches: list[MatchResult] = []
    seen_pairs: set[tuple[str, str]] = set()

    exact_matches = _find_exact_matches(entities)
    matches.extend(exact_matches)
    for m in exact_matches:
        seen_pairs.add((m.entity_a_id, m.entity_b_id))

    try:
        from rapidfuzz import fuzz
        fuzzy_matches = _find_fuzzy_matches(entities, fuzz, fuzzy_threshold, seen_pairs)
        matches.extend(fuzzy_matches)
        for m in fuzzy_matches:
            seen_pairs.add((m.entity_a_id, m.entity_b_id))
    except ImportError:
        logger.warning("rapidfuzz not installed, skipping fuzzy matching")

    embedded = [e for e in entities if e.get("embedding")]
    if len(embedded) > 1:
        semantic_matches = _find_semantic_matches(embedded, cosine_threshold, seen_pairs)
        matches.extend(semantic_matches)
        for m in semantic_matches:
            seen_pairs.add((m.entity_a_id, m.entity_b_id))

    if use_llm:
        ambiguous = [m for m in matches if m.match_type == "fuzzy" and m.score < 90]
        if ambiguous:
            confirmed = _llm_disambiguate(ambiguous, model_config=model_config)
            for m in matches:
                if any(c.entity_a_id == m.entity_a_id and c.entity_b_id == m.entity_b_id for c in confirmed):
                    m.match_type = "llm_confirmed"

    logger.info(
        "matching_complete total=%d exact=%d fuzzy=%d semantic=%d",
        len(matches),
        sum(1 for m in matches if m.match_type == "exact"),
        sum(1 for m in matches if m.match_type in ("fuzzy", "llm_confirmed")),
        sum(1 for m in matches if m.match_type == "semantic"),
    )
    return matches


def _find_exact_matches(entities: list[dict]) -> list[MatchResult]:
    by_name: dict[str, list[dict]] = {}
    for e in entities:
        key = e["name"].lower().strip()
        by_name.setdefault(key, []).append(e)

    matches = []
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                if group[i].get("source_document_id") == group[j].get("source_document_id"):
                    continue
                matches.append(MatchResult(
                    entity_a_id=group[i]["id"],
                    entity_b_id=group[j]["id"],
                    entity_a_name=group[i]["name"],
                    entity_b_name=group[j]["name"],
                    match_type="exact",
                    score=100.0,
                    relationship="SAME_AS",
                ))
    return matches


def _find_fuzzy_matches(entities, fuzz, threshold, seen_pairs) -> list[MatchResult]:
    matches = []
    names = [(e["id"], e["name"], e.get("entity_type", "")) for e in entities]

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            pair_key = (names[i][0], names[j][0])
            if pair_key in seen_pairs:
                continue
            if names[i][2] != names[j][2]:
                continue

            score = fuzz.ratio(names[i][1].lower(), names[j][1].lower())
            if score >= threshold:
                relationship = "SAME_AS" if score >= 95 else "RELATED_TO"
                matches.append(MatchResult(
                    entity_a_id=names[i][0],
                    entity_b_id=names[j][0],
                    entity_a_name=names[i][1],
                    entity_b_name=names[j][1],
                    match_type="fuzzy",
                    score=score,
                    relationship=relationship,
                ))
    return matches


def _find_semantic_matches(entities, threshold, seen_pairs) -> list[MatchResult]:
    import numpy as np

    matches = []
    ids = [e["id"] for e in entities]
    names = [e["name"] for e in entities]
    embeddings = np.array([e["embedding"] for e in entities])

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = embeddings / norms
    similarity_matrix = normalized @ normalized.T

    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if (ids[i], ids[j]) in seen_pairs:
                continue
            score = float(similarity_matrix[i, j])
            if score >= threshold:
                matches.append(MatchResult(
                    entity_a_id=ids[i],
                    entity_b_id=ids[j],
                    entity_a_name=names[i],
                    entity_b_name=names[j],
                    match_type="semantic",
                    score=score * 100,
                    relationship="RELATED_TO",
                ))
    return matches


def _llm_disambiguate(ambiguous: list[MatchResult], model_config: dict | None = None) -> list[MatchResult]:
    """Use LLM to confirm or reject ambiguous entity matches."""
    from app.services.ai.router import llm_call, parse_json_response

    pairs_text = "\n".join(
        f'{i+1}. "{m.entity_a_name}" vs "{m.entity_b_name}" (score: {m.score:.0f})'
        for i, m in enumerate(ambiguous[:20])
    )

    prompt = f"""Given these entity pairs found in business documents, determine which pairs refer to the same thing.

{pairs_text}

Return a JSON array of pair numbers that ARE the same entity. Example: [1, 3, 5]
Only include pairs you are confident about."""

    try:
        result = llm_call(
            prompt=prompt, max_tokens=200, tier="fast",
            operation="process_matching", model_config=model_config,
        )
        confirmed_indices = parse_json_response(result.text)
        if isinstance(confirmed_indices, list):
            return [ambiguous[i - 1] for i in confirmed_indices if 0 < i <= len(ambiguous)]
    except Exception:
        logger.warning("llm_disambiguate_failed")

    return []
