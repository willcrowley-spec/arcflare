"""Phase 2: SerpAPI web search enrichment with Redis caching.

Generates targeted search queries about the organization and fetches
results to supplement the website crawl with external intelligence.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.services.research.crawler import CrawledPage, _fetch_page

logger = logging.getLogger(__name__)

SEARCH_QUERY_TEMPLATES = [
    '"{name}" company overview',
    '"{name}" revenue employees funding',
    '"{name}" customers case study',
    '"{name}" site:linkedin.com/company',
    '"{name}" site:crunchbase.com',
    '"{name}" competitors market',
    '"{name}" leadership team executives',
    '"{name}" technology stack integrations',
    '"{name}" pricing plans',
    '"{name}" series funding raised',
]

MAX_RESULTS_PER_QUERY = 5
MAX_FETCH_PER_QUERY = 3


@dataclass
class SearchResult:
    title: str
    snippet: str
    url: str
    query: str


def _cache_key(query: str) -> str:
    return f"serpapi:{hashlib.sha256(query.encode()).hexdigest()[:16]}"


def _get_cached(r, query: str) -> list[dict] | None:
    """Check Redis for cached search results."""
    if r is None:
        return None
    try:
        raw = r.get(_cache_key(query))
        if raw:
            return json.loads(raw)
    except Exception:
        logger.debug("search_cache_miss query=%s", query[:60])
    return None


def _set_cached(r, query: str, results: list[dict], ttl: int = 86400) -> None:
    """Cache search results in Redis for 24h."""
    if r is None:
        return
    try:
        r.set(_cache_key(query), json.dumps(results), ex=ttl)
    except Exception:
        logger.debug("search_cache_write_failed query=%s", query[:60])


def _search_serpapi(query: str, api_key: str) -> list[SearchResult]:
    """Execute a SerpAPI Google search."""
    try:
        resp = httpx.get(
            "https://serpapi.com/search",
            params={
                "q": query,
                "api_key": api_key,
                "engine": "google",
                "num": 10,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("serpapi_failed query=%s error=%s", query[:60], e)
        return []

    results = []
    for item in data.get("organic_results", []):
        results.append(SearchResult(
            title=item.get("title", ""),
            snippet=item.get("snippet", ""),
            url=item.get("link", ""),
            query=query,
        ))

    return results


def search_and_fetch(
    company_name: str,
    existing_urls: set[str] | None = None,
) -> tuple[list[SearchResult], list[CrawledPage]]:
    """Run all search queries, fetch top results, return both raw results and fetched pages.

    Args:
        company_name: The org name to research.
        existing_urls: URLs already crawled in Phase 1 (skip these).

    Returns:
        Tuple of (all search results, fetched pages from top results).
    """
    settings = get_settings()
    api_key = settings.SERPAPI_KEY

    if not api_key:
        logger.warning("serpapi_key_not_configured — skipping search enrichment")
        return [], []

    try:
        from app.services.sync_progress import get_redis_client
        redis = get_redis_client()
    except Exception:
        redis = None

    seen_urls = set(existing_urls or set())
    all_results: list[SearchResult] = []
    fetched_pages: list[CrawledPage] = []

    queries = [t.format(name=company_name) for t in SEARCH_QUERY_TEMPLATES]

    for query in queries:
        cached = _get_cached(redis, query)
        if cached:
            results = [SearchResult(**r) for r in cached]
            logger.debug("search_cache_hit query=%s results=%d", query[:60], len(results))
        else:
            results = _search_serpapi(query, api_key)
            if results:
                _set_cached(redis, query, [
                    {"title": r.title, "snippet": r.snippet, "url": r.url, "query": r.query}
                    for r in results
                ])
            logger.info("search_complete query=%s results=%d", query[:60], len(results))

        all_results.extend(results)

        fetched_count = 0
        for result in results[:MAX_RESULTS_PER_QUERY]:
            if fetched_count >= MAX_FETCH_PER_QUERY:
                break
            if not result.url or result.url in seen_urls:
                continue

            skip_domains = ("linkedin.com", "facebook.com", "twitter.com", "x.com",
                            "instagram.com", "youtube.com", "tiktok.com")
            if any(d in result.url.lower() for d in skip_domains):
                continue

            page = _fetch_page(result.url)
            if page:
                seen_urls.add(result.url)
                fetched_pages.append(page)
                fetched_count += 1

    logger.info(
        "search_enrichment_complete company=%s queries=%d results=%d fetched=%d",
        company_name, len(queries), len(all_results), len(fetched_pages),
    )
    return all_results, fetched_pages
