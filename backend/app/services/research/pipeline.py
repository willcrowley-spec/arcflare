"""Org research pipeline orchestrator.

Connects all six phases: crawl -> search -> extract -> verify -> assemble -> vectorize.
Manages progress reporting, error handling, and persistence.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.org_research import OrgResearchProfile
from app.models.organization import Organization

logger = logging.getLogger(__name__)


async def run_org_research_pipeline(
    org_id: UUID,
    db: AsyncSession,
    progress_cb: Callable[[str, str, int, int], None] | None = None,
    model_config: dict | None = None,
) -> OrgResearchProfile:
    """Execute the full org research pipeline.

    Args:
        org_id: Organization to research.
        db: Async database session.
        progress_cb: Optional callback(phase, status, count, total).
        model_config: Org analysis_config for model overrides.

    Returns:
        Persisted OrgResearchProfile with complete results.
    """
    import asyncio

    def _update(phase: str, status: str, count: int = 0, total: int = 0) -> None:
        if progress_cb:
            progress_cb(phase, status, count, total)

    org = await db.get(Organization, org_id)
    if not org:
        raise ValueError(f"Organization {org_id} not found")

    settings = org.settings_json or {}
    domains = settings.get("domains", [])
    company_name = org.name

    if not domains:
        raise ValueError(
            f"No domains configured for org {org_id}. "
            "Add domains to organization settings before running research."
        )

    research = OrgResearchProfile(org_id=org_id, status="researching")
    db.add(research)
    await db.flush()
    research_log: dict = {"phases": {}, "started_at": datetime.now(tz=timezone.utc).isoformat()}

    try:
        # ============================================================
        # Phase 1: Website Crawl
        # ============================================================
        _update("crawl", "running", 0, len(domains))
        logger.info("research_phase1_start org=%s domains=%s", org_id, domains)

        from app.services.research.crawler import crawl_domains, extract_structured_profile_hints

        crawled_pages = await asyncio.to_thread(crawl_domains, domains)
        structured_hints = extract_structured_profile_hints(crawled_pages)

        research_log["phases"]["crawl"] = {
            "pages": len(crawled_pages),
            "domains": domains,
        }
        _update("crawl", "done", len(crawled_pages), len(crawled_pages))
        logger.info("research_phase1_complete org=%s pages=%d", org_id, len(crawled_pages))

        # ============================================================
        # Phase 2: Search Enrichment
        # ============================================================
        _update("search", "running", 0, 1)
        logger.info("research_phase2_start org=%s", org_id)

        from app.services.research.searcher import search_and_fetch

        crawled_urls = {p.url for p in crawled_pages}
        search_results, search_pages = await asyncio.to_thread(
            search_and_fetch, company_name, crawled_urls,
        )

        all_pages = crawled_pages + search_pages

        research_log["phases"]["search"] = {
            "queries": len(search_results),
            "pages_fetched": len(search_pages),
        }
        _update("search", "done", len(search_results), len(search_results))
        logger.info(
            "research_phase2_complete org=%s results=%d fetched=%d",
            org_id, len(search_results), len(search_pages),
        )

        from app.services.prompts.resolver import resolve_prompt_blocks

        extraction_blocks = await resolve_prompt_blocks("org_research_extraction", org_id, db)
        verification_blocks = await resolve_prompt_blocks("org_research_verification", org_id, db)
        synthesis_blocks = await resolve_prompt_blocks("org_research_synthesis", org_id, db)

        # ============================================================
        # Phase 3: Fact Extraction
        # ============================================================
        _update("extraction", "running", 0, len(all_pages))
        logger.info("research_phase3_start org=%s pages=%d", org_id, len(all_pages))

        from app.services.research.extractor import extract_facts

        facts = await asyncio.to_thread(
            extract_facts, all_pages, company_name, search_results, model_config,
            extraction_blocks,
        )

        research_log["phases"]["extraction"] = {"facts": len(facts)}
        _update("extraction", "done", len(facts), len(facts))
        logger.info("research_phase3_complete org=%s facts=%d", org_id, len(facts))

        # ============================================================
        # Phase 4: Fact Verification
        # ============================================================
        _update("verification", "running", 0, len(facts))
        logger.info("research_phase4_start org=%s facts=%d", org_id, len(facts))

        from app.services.research.verifier import verify_facts

        verified_facts = await asyncio.to_thread(
            verify_facts, facts, model_config, verification_blocks,
        )

        research_log["phases"]["verification"] = {
            "input_facts": len(facts),
            "output_facts": len(verified_facts),
            "confirmed": sum(1 for f in verified_facts if f.verification_status == "confirmed"),
            "weak": sum(1 for f in verified_facts if f.verification_status == "weak"),
        }
        _update("verification", "done", len(verified_facts), len(verified_facts))
        logger.info(
            "research_phase4_complete org=%s kept=%d",
            org_id, len(verified_facts),
        )

        # ============================================================
        # Phase 5: Profile Assembly
        # ============================================================
        _update("assembly", "running", 0, 1)
        logger.info("research_phase5_start org=%s", org_id)

        from app.services.research.assembler import assemble_profile, build_enrichment_summary

        profile = await asyncio.to_thread(
            assemble_profile,
            verified_facts, all_pages, search_results,
            structured_hints, company_name, domains, model_config,
            synthesis_blocks,
        )

        enrichment = build_enrichment_summary(profile)
        enrichment["research_profile_id"] = str(research.id)

        research.profile_json = profile
        research.sources_json = [
            {
                "url": f.source_urls[0] if f.source_urls else "",
                "title": f.source_titles[0] if f.source_titles else "",
                "claim": f.claim,
                "category": f.category,
                "confidence": f.confidence,
                "verification": f.verification_status,
            }
            for f in verified_facts
        ]
        research.facts_json = [
            {
                "category": f.category,
                "claim": f.claim,
                "confidence": f.confidence,
                "verification_status": f.verification_status,
                "source_urls": f.source_urls,
            }
            for f in verified_facts
        ]
        research.company_summary = profile.get("company_summary", "")
        research.industry = (profile.get("overview", {}).get("industry") or "")[:255]
        research.employee_range = (profile.get("size_and_scale", {}).get("employee_range") or "")[:100]
        research.revenue_range = (profile.get("size_and_scale", {}).get("revenue_range") or "")[:100]

        settings["enrichment"] = enrichment
        org.settings_json = settings
        await db.flush()

        research_log["phases"]["assembly"] = {"profile_sections": len(profile)}
        _update("assembly", "done", 1, 1)
        logger.info("research_phase5_complete org=%s", org_id)

        # ============================================================
        # Phase 6: Vectorization
        # ============================================================
        _update("vectorization", "running", 0, 1)
        logger.info("research_phase6_start org=%s", org_id)

        from app.services.research.vectorizer import vectorize_research_profile

        chunk_count = await vectorize_research_profile(org_id, profile, company_name, db)

        research_log["phases"]["vectorization"] = {"chunks": chunk_count}
        _update("vectorization", "done", chunk_count, chunk_count)
        logger.info("research_phase6_complete org=%s chunks=%d", org_id, chunk_count)

        # ============================================================
        # Finalize
        # ============================================================
        research.status = "completed"
        research.completed_at = datetime.now(tz=timezone.utc)
        research_log["completed_at"] = research.completed_at.isoformat()
        research.research_log_json = research_log
        await db.commit()

        logger.info(
            "research_pipeline_complete org=%s profile_id=%s facts=%d pages=%d",
            org_id, research.id, len(verified_facts), len(all_pages),
        )
        return research

    except Exception as exc:
        logger.exception("research_pipeline_failed org=%s", org_id)
        try:
            research.status = "failed"
            research_log["error"] = str(exc)[:2000]
            research_log["failed_at"] = datetime.now(tz=timezone.utc).isoformat()
            research.research_log_json = research_log
            await db.commit()
        except Exception:
            logger.exception("research_status_update_failed org=%s", org_id)
        raise
