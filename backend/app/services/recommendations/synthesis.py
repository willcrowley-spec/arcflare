"""Business process synthesis using LLM-powered clustering and generation.

Clusters related entities, then uses LLM to generate business process
documents with test cases and full source lineage tracking.
"""
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BusinessProcessDoc:
    title: str
    summary: str
    steps: list[dict]
    test_cases: list[dict]
    source_entity_ids: list[str] = field(default_factory=list)
    source_document_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0


def cluster_entities(
    entities: list[dict],
    min_cluster_size: int = 3,
) -> list[list[dict]]:
    """Cluster entities by embedding similarity using HDBSCAN.

    Args:
        entities: List of dicts with 'id', 'name', 'entity_type', 'embedding'.
        min_cluster_size: Minimum entities per cluster.

    Returns:
        List of entity clusters (each cluster is a list of entity dicts).
    """
    embedded = [e for e in entities if e.get("embedding")]
    if len(embedded) < min_cluster_size:
        return [embedded] if embedded else []

    try:
        import numpy as np
        from sklearn.cluster import HDBSCAN

        embeddings = np.array([e["embedding"] for e in embedded])

        clusterer = HDBSCAN(
            min_cluster_size=min_cluster_size,
            metric="euclidean",
        )
        labels = clusterer.fit_predict(embeddings)

        clusters: dict[int, list[dict]] = {}
        for entity, label in zip(embedded, labels):
            if label == -1:
                continue
            clusters.setdefault(label, []).append(entity)

        result = [c for c in clusters.values() if len(c) >= min_cluster_size]
        logger.info("clustering_complete clusters=%d noise=%d", len(result), sum(1 for l in labels if l == -1))
        return result

    except ImportError:
        logger.warning("hdbscan/sklearn not available, returning all entities as single cluster")
        return [embedded]


def generate_process_document(
    cluster: list[dict],
    context_chunks: list[str] | None = None,
) -> BusinessProcessDoc | None:
    """Generate a business process document from a cluster of related entities.

    Args:
        cluster: List of entity dicts in the cluster.
        context_chunks: Optional text chunks for additional context.

    Returns:
        BusinessProcessDoc or None if generation fails.
    """
    from app.services.ai.router import llm_call, parse_json_response

    entity_summary = "\n".join(
        f"- {e['name']} ({e.get('entity_type', 'unknown')}): {e.get('description', 'N/A')}"
        for e in cluster
    )

    context = ""
    if context_chunks:
        context = "\n\nRelevant document excerpts:\n" + "\n---\n".join(context_chunks[:5])

    prompt = f"""Based on these related business entities, generate a business process document.

Entities:
{entity_summary}
{context}

Return ONLY a JSON object:
{{
    "title": "Process name",
    "summary": "2-3 sentence description of this business process",
    "steps": [
        {{"step_number": 1, "action": "What happens", "actor": "Who does it", "system": "Which system"}}
    ],
    "test_cases": [
        {{"title": "Test case name", "scenario": "Given/When/Then", "expected_outcome": "What should happen"}}
    ],
    "confidence": 0.0 to 1.0
}}"""

    try:
        result = llm_call(prompt=prompt, max_tokens=3000, tier="strong")
        data = parse_json_response(result.text)

        return BusinessProcessDoc(
            title=data.get("title", "Unnamed Process"),
            summary=data.get("summary", ""),
            steps=data.get("steps", []),
            test_cases=data.get("test_cases", []),
            source_entity_ids=[e["id"] for e in cluster],
            source_document_ids=list({e.get("source_document_id", "") for e in cluster if e.get("source_document_id")}),
            confidence=float(data.get("confidence", 0.5)),
        )
    except Exception as e:
        logger.error("process_generation_failed error=%s", e)
        return None


def synthesize_processes(
    entities: list[dict],
    context_chunks: list[str] | None = None,
    min_cluster_size: int = 3,
) -> list[BusinessProcessDoc]:
    """Full synthesis pipeline: cluster entities, then generate process docs.

    Args:
        entities: All extracted entities with embeddings.
        context_chunks: Optional text chunks for LLM context.
        min_cluster_size: Minimum entities per cluster.

    Returns:
        List of generated BusinessProcessDoc objects.
    """
    clusters = cluster_entities(entities, min_cluster_size)
    logger.info("synthesis_start clusters=%d", len(clusters))

    docs: list[BusinessProcessDoc] = []
    for i, cluster in enumerate(clusters):
        logger.info("generating_process cluster=%d/%d entities=%d", i + 1, len(clusters), len(cluster))
        doc = generate_process_document(cluster, context_chunks)
        if doc:
            docs.append(doc)

    logger.info("synthesis_complete processes=%d", len(docs))
    return docs
