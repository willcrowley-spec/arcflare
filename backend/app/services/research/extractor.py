"""Phase 3: LLM-based fact extraction from crawled and searched pages.

Batches pages into groups and extracts categorized, cited facts using
the existing llm_call() + JSON schema infrastructure.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.services.ai.router import PromptParts, llm_call, parse_json_response
from app.services.research.crawler import CrawledPage
from app.services.research.searcher import SearchResult

logger = logging.getLogger(__name__)

BATCH_SIZE = 5


@dataclass
class ExtractedFact:
    category: str
    claim: str
    evidence_refs: list[str]
    confidence: float
    source_urls: list[str] = field(default_factory=list)
    source_titles: list[str] = field(default_factory=list)
    source_excerpts: list[str] = field(default_factory=list)
    verification_status: str = "unverified"


def _build_page_block(idx: int, page: CrawledPage) -> str:
    """Format a single page for the extraction prompt."""
    text = page.text[:3000]
    return f"[PAGE-{idx}] URL: {page.url}\nTitle: {page.title}\nType: {page.page_type}\n---\n{text}\n"


def _build_search_context(results: list[SearchResult]) -> str:
    """Build a context block from search result snippets (no full page text)."""
    if not results:
        return ""
    lines = ["SEARCH RESULT SNIPPETS (for additional context, not primary sources):"]
    for r in results[:15]:
        if r.snippet:
            lines.append(f"- {r.title}: {r.snippet} ({r.url})")
    return "\n".join(lines)


def extract_facts(
    pages: list[CrawledPage],
    company_name: str,
    search_results: list[SearchResult] | None = None,
    model_config: dict | None = None,
    prompt_blocks: dict[str, str] | None = None,
) -> list[ExtractedFact]:
    """Extract facts from pages in batches. Returns deduplicated fact list.

    Pages are tagged with reference IDs ([PAGE-0], [PAGE-1], etc.) that the LLM
    cites in its output. Post-processing resolves refs back to actual URLs.
    """
    if not pages:
        return []

    page_index: dict[str, CrawledPage] = {}
    all_facts: list[ExtractedFact] = []

    search_context = _build_search_context(search_results or [])

    for batch_start in range(0, len(pages), BATCH_SIZE):
        batch = pages[batch_start:batch_start + BATCH_SIZE]
        page_blocks = []

        for i, page in enumerate(batch):
            ref_id = f"PAGE-{batch_start + i}"
            page_index[ref_id] = page
            page_blocks.append(_build_page_block(batch_start + i, page))

        system = (prompt_blocks or {}).get("instructions") or ""
        protocol = (prompt_blocks or {}).get("protocol") or ""
        prompt = PromptParts(
            system=system,
            context=search_context if search_context else "",
            variable=protocol.format(
                company_name=company_name,
                page_blocks="\n\n".join(page_blocks),
            ),
        )

        try:
            result = llm_call(
                prompt,
                max_tokens=4096,
                tier="fast",
                operation="org_research_extraction",
                model_config=model_config,
            )
            parsed = parse_json_response(result.text)
        except Exception as e:
            logger.warning(
                "extraction_failed batch=%d-%d error=%s",
                batch_start, batch_start + len(batch), e,
            )
            continue

        raw_facts = parsed.get("facts", []) if isinstance(parsed, dict) else []

        for rf in raw_facts:
            if not isinstance(rf, dict) or not rf.get("claim"):
                continue

            refs = rf.get("evidence_refs", [])
            if isinstance(refs, str):
                refs = [refs]

            source_urls = []
            source_titles = []
            source_excerpts = []
            for ref in refs:
                page = page_index.get(ref)
                if page:
                    source_urls.append(page.url)
                    source_titles.append(page.title)
                    source_excerpts.append(page.text[:300])

            fact = ExtractedFact(
                category=_normalize_category(rf.get("category", "overview")),
                claim=rf["claim"],
                evidence_refs=refs,
                confidence=min(1.0, max(0.0, float(rf.get("confidence", 0.5)))),
                source_urls=source_urls,
                source_titles=source_titles,
                source_excerpts=source_excerpts,
            )
            all_facts.append(fact)

        logger.info(
            "extraction_batch_complete batch=%d-%d facts=%d",
            batch_start, batch_start + len(batch), len(raw_facts),
        )

    deduped = _deduplicate_facts(all_facts)
    logger.info(
        "extraction_complete company=%s total_facts=%d deduped=%d",
        company_name, len(all_facts), len(deduped),
    )
    return deduped


VALID_CATEGORIES = frozenset({
    "overview", "financials", "products", "icp", "structure",
    "technology", "market", "employees",
})

_CATEGORY_ALIASES: dict[str, str] = {
    "company": "overview", "about": "overview", "description": "overview",
    "mission": "overview", "history": "overview", "founding": "overview",
    "revenue": "financials", "funding": "financials", "valuation": "financials",
    "business_model": "financials", "growth": "financials", "metrics": "financials",
    "pricing": "products", "services": "products", "platform": "products",
    "features": "products", "solutions": "products",
    "customers": "icp", "target_market": "icp", "personas": "icp",
    "use_cases": "icp", "segments": "icp",
    "leadership": "structure", "executives": "structure", "board": "structure",
    "departments": "structure", "subsidiaries": "structure", "corporate": "structure",
    "tech": "technology", "stack": "technology", "integrations": "technology",
    "tools": "technology", "infrastructure": "technology",
    "competitors": "market", "awards": "market", "press": "market",
    "partnerships": "market", "recognition": "market",
    "hiring": "employees", "headcount": "employees", "culture": "employees",
    "offices": "employees", "team_size": "employees",
}


def _normalize_category(raw: str) -> str:
    if not raw:
        return "overview"
    cleaned = raw.lower().strip().replace(" ", "_")
    if cleaned in VALID_CATEGORIES:
        return cleaned
    return _CATEGORY_ALIASES.get(cleaned, "overview")


def _deduplicate_facts(facts: list[ExtractedFact]) -> list[ExtractedFact]:
    """Remove near-duplicate facts using token overlap."""
    stop_words = {"the", "a", "an", "of", "for", "in", "on", "to", "and",
                  "is", "was", "by", "with", "at", "from", "their", "they",
                  "has", "have", "are", "its", "this", "that", "it"}

    def _tokens(text: str) -> set[str]:
        import re
        return {w for w in re.sub(r"[^a-z0-9 ]", "", text.lower()).split()
                if w not in stop_words and len(w) > 2}

    unique: list[ExtractedFact] = []
    seen_tokens: list[set[str]] = []

    for f in facts:
        ft = _tokens(f.claim)
        if not ft:
            unique.append(f)
            seen_tokens.append(set())
            continue

        is_dup = False
        for existing in seen_tokens:
            if not existing:
                continue
            overlap = ft & existing
            similarity = len(overlap) / min(len(ft), len(existing))
            if similarity > 0.65:
                is_dup = True
                break

        if not is_dup:
            unique.append(f)
            seen_tokens.append(ft)

    return unique
