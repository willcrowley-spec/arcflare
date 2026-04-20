"""Phase 5: Profile assembly from verified facts.

Groups facts by category, selects highest-confidence values, and uses
one LLM call for narrative synthesis. Denormalizes key fields into
settings_json["enrichment"] for the discovery pipeline.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from app.services.ai.router import PromptParts, llm_call, parse_json_response
from app.services.research.crawler import CrawledPage
from app.services.research.extractor import ExtractedFact
from app.services.research.searcher import SearchResult

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM_PROMPT = """\
You are a senior business analyst writing an executive intelligence brief about a company.
Given a set of verified facts organized by category, produce:

1. company_summary: A 2-4 paragraph executive overview of what the company does, \
who they serve, their market position, and notable characteristics. Write in third person, \
professional tone. Only include information supported by the provided facts.

2. ideal_customer_profile: A structured analysis of who the company sells to, including:
   - segments: Target market segments (e.g. "Mid-market B2B SaaS")
   - buyer_personas: Key buyer roles (e.g. "VP Sales Ops")
   - value_propositions: Core value props as the customer would describe them
   - competitive_positioning: How they differentiate from competitors

3. financial_analysis: Speculation flag = true. Based on available signals, estimate:
   - business_model: How they make money
   - pricing_model: Pricing structure if visible
   - growth_indicators: Signals of growth or contraction
   - revenue_drivers: Key revenue levers

Return a JSON object with keys: company_summary, ideal_customer_profile, financial_analysis."""


def _group_facts_by_category(facts: list[ExtractedFact]) -> dict[str, list[ExtractedFact]]:
    groups: dict[str, list[ExtractedFact]] = defaultdict(list)
    for f in facts:
        groups[f.category].append(f)
    for category in groups:
        groups[category].sort(key=lambda f: f.confidence, reverse=True)
    return groups


def _build_facts_context(grouped: dict[str, list[ExtractedFact]]) -> str:
    """Build a compact text representation of facts for the synthesis prompt."""
    lines = []
    for category, facts in sorted(grouped.items()):
        lines.append(f"\n## {category.upper()}")
        for f in facts[:10]:
            status = f"[{f.verification_status}]" if f.verification_status != "unverified" else ""
            lines.append(f"- {f.claim} (confidence: {f.confidence:.2f}) {status}")
    return "\n".join(lines)


def _extract_field(grouped: dict[str, list[ExtractedFact]], category: str, keywords: list[str]) -> str | None:
    """Find the best fact matching keywords in a category."""
    facts = grouped.get(category, [])
    for kw in keywords:
        for f in facts:
            if kw.lower() in f.claim.lower() and f.confidence >= 0.5:
                return f.claim
    return None


def _collect_sources(facts: list[ExtractedFact]) -> list[dict]:
    """Build the sources array for the profile."""
    sources: list[dict] = []
    seen_urls: set[str] = set()

    for fact in facts:
        for i, url in enumerate(fact.source_urls):
            if url in seen_urls:
                continue
            seen_urls.add(url)
            sources.append({
                "url": url,
                "title": fact.source_titles[i] if i < len(fact.source_titles) else "",
                "excerpt": fact.source_excerpts[i][:200] if i < len(fact.source_excerpts) else "",
                "confidence": fact.confidence,
            })

    return sources


def assemble_profile(
    facts: list[ExtractedFact],
    pages: list[CrawledPage],
    search_results: list[SearchResult],
    structured_hints: dict,
    company_name: str,
    domains: list[str],
    model_config: dict | None = None,
) -> dict:
    """Assemble the full org research profile from verified facts.

    Returns the complete profile_json dict ready for storage.
    """
    grouped = _group_facts_by_category(facts)
    facts_context = _build_facts_context(grouped)

    # --- LLM synthesis for narratives ---
    synthesis = {}
    try:
        prompt = PromptParts(
            system=SYNTHESIS_SYSTEM_PROMPT,
            variable=f"Company: {company_name}\n\nVERIFIED FACTS:\n{facts_context}",
        )
        result = llm_call(
            prompt,
            max_tokens=3000,
            tier="fast",
            operation="org_research_synthesis",
            model_config=model_config,
        )
        synthesis = parse_json_response(result.text)
        if not isinstance(synthesis, dict):
            synthesis = {}
    except Exception as e:
        logger.warning("synthesis_failed company=%s error=%s", company_name, e)

    # --- Build structured profile ---
    all_sources = _collect_sources(facts)

    names = structured_hints.get("names", [])
    display_name = names[0] if names else company_name

    overview_facts = grouped.get("overview", [])
    description = ""
    for f in overview_facts:
        if len(f.claim) > 50 and f.confidence >= 0.6:
            description = f.claim
            break
    if not description and structured_hints.get("descriptions"):
        description = structured_hints["descriptions"][0]

    profile: dict = {
        "overview": {
            "name": display_name,
            "description": description,
            "founded": _extract_field(grouped, "overview", ["founded", "established", "started"]),
            "headquarters": _extract_field(grouped, "overview", ["headquarter", "based in", "located"]),
            "industry": _extract_field(grouped, "overview", ["industry", "sector", "space"]),
            "sub_industry": None,
        },
        "size_and_scale": {
            "employee_range": _extract_field(grouped, "employees", ["employee", "headcount", "team", "people"]),
            "revenue_range": _extract_field(grouped, "financials", ["revenue", "arr", "annual"]),
            "funding_stage": _extract_field(grouped, "financials", ["series", "stage", "round"]),
            "total_funding": _extract_field(grouped, "financials", ["raised", "funding", "capital"]),
            "growth_signals": [
                f.claim for f in grouped.get("financials", [])
                if any(kw in f.claim.lower() for kw in ("growth", "growing", "hiring", "expand"))
                and f.confidence >= 0.5
            ][:5],
            "sources": [s for s in all_sources if any(
                kw in s.get("title", "").lower()
                for kw in ("funding", "revenue", "crunchbase", "employee")
            )][:5],
        },
        "products_and_services": [
            {
                "name": f.claim.split(":")[0] if ":" in f.claim else f.claim[:60],
                "description": f.claim,
                "sources": [{"url": u} for u in f.source_urls[:2]],
            }
            for f in grouped.get("products", [])[:8]
            if f.confidence >= 0.5
        ],
        "ideal_customer_profile": synthesis.get("ideal_customer_profile", {
            "segments": [],
            "buyer_personas": [],
            "value_propositions": [],
            "competitive_positioning": "",
        }),
        "corporate_structure": {
            "parent_company": _extract_field(grouped, "structure", ["parent", "subsidiary of", "owned by"]),
            "subsidiaries": [
                f.claim for f in grouped.get("structure", [])
                if "subsidiary" in f.claim.lower() or "acquired" in f.claim.lower()
            ][:5],
            "key_executives": [
                {"name": f.claim, "source": f.source_urls[0] if f.source_urls else ""}
                for f in grouped.get("structure", [])
                if any(t in f.claim.lower() for t in ("ceo", "cto", "cfo", "coo", "vp", "president",
                                                       "founder", "chief", "director", "head of"))
                and f.confidence >= 0.5
            ][:10],
            "departments_mentioned": list({
                f.claim for f in grouped.get("structure", [])
                if any(d in f.claim.lower() for d in ("department", "team", "division", "group"))
            })[:10],
            "sources": [s for s in all_sources if any(
                kw in s.get("title", "").lower()
                for kw in ("team", "about", "leadership", "executive")
            )][:5],
        },
        "technology_stack": {
            "mentioned_technologies": [
                f.claim for f in grouped.get("technology", [])[:15]
                if f.confidence >= 0.5
            ],
            "integrations": [
                f.claim for f in grouped.get("technology", [])
                if "integrat" in f.claim.lower()
            ][:10],
            "sources": [s for s in all_sources if any(
                kw in s.get("title", "").lower()
                for kw in ("tech", "stack", "integrat", "platform")
            )][:5],
        },
        "financial_drivers": synthesis.get("financial_analysis", {
            "business_model": _extract_field(grouped, "financials", ["model", "saas", "subscription"]),
            "pricing_model": _extract_field(grouped, "financials", ["pricing", "per-seat", "tier"]),
            "growth_indicators": [],
            "revenue_drivers": [],
            "is_speculative": True,
        }),
        "market_presence": {
            "social_profiles": structured_hints.get("social_links", {}),
            "press_mentions": [
                {"title": f.claim, "url": f.source_urls[0] if f.source_urls else ""}
                for f in grouped.get("market", [])
                if any(kw in f.claim.lower() for kw in ("press", "news", "announce", "launch"))
                and f.confidence >= 0.5
            ][:10],
            "awards_recognition": [
                f.claim for f in grouped.get("market", [])
                if any(kw in f.claim.lower() for kw in ("award", "recogni", "leader", "winner"))
            ][:5],
            "sources": [s for s in all_sources if any(
                kw in s.get("title", "").lower()
                for kw in ("news", "press", "award", "partner")
            )][:5],
        },
        "company_summary": synthesis.get("company_summary", description),
        "research_metadata": {
            "completed_at": datetime.now(tz=timezone.utc).isoformat(),
            "domains_crawled": domains,
            "pages_analyzed": len(pages),
            "search_results_found": len(search_results),
            "facts_extracted": len(facts),
            "facts_verified": sum(1 for f in facts if f.verification_status == "confirmed"),
            "facts_weak": sum(1 for f in facts if f.verification_status == "weak"),
            "verification_rate": (
                sum(1 for f in facts if f.verification_status == "confirmed") / max(len(facts), 1)
            ),
            "total_sources": len(all_sources),
        },
    }

    return profile


def build_enrichment_summary(profile: dict) -> dict:
    """Extract the compact enrichment dict for settings_json["enrichment"].

    This is the subset of the profile that the discovery pipeline reads
    via gather_org_context().
    """
    overview = profile.get("overview", {})
    size = profile.get("size_and_scale", {})
    icp = profile.get("ideal_customer_profile", {})
    fin = profile.get("financial_drivers", {})
    tech = profile.get("technology_stack", {})
    meta = profile.get("research_metadata", {})

    products = [p.get("name", "") for p in profile.get("products_and_services", [])]

    return {
        "company_summary": profile.get("company_summary", ""),
        "industry": overview.get("industry"),
        "sub_industry": overview.get("sub_industry"),
        "business_model": fin.get("business_model") if isinstance(fin, dict) else None,
        "products": products[:10],
        "icp_segments": icp.get("segments", []) if isinstance(icp, dict) else [],
        "employee_range": size.get("employee_range"),
        "revenue_range": size.get("revenue_range"),
        "key_technologies": tech.get("mentioned_technologies", [])[:10],
        "research_completed_at": meta.get("completed_at"),
        "research_profile_id": None,
    }
