"""Phase 4: Batch fact verification against source text.

Checks whether extracted claims are actually supported by their cited sources.
Adapted from Liams-Revenge FactValidator pattern, batched for efficiency.
"""
from __future__ import annotations

import logging

from app.services.ai.router import PromptParts, llm_call, parse_json_response
from app.services.research.extractor import ExtractedFact

logger = logging.getLogger(__name__)

BATCH_SIZE = 15
CONFIDENCE_PENALTY_WEAK = 0.7
CONFIDENCE_PENALTY_UNSUPPORTED = 0.2


def verify_facts(
    facts: list[ExtractedFact],
    model_config: dict | None = None,
    prompt_blocks: dict[str, str] | None = None,
) -> list[ExtractedFact]:
    """Verify facts against their source excerpts in batches.

    Modifies facts in-place: updates confidence scores and verification_status.
    Drops facts with UNSUPPORTED verdicts (confidence goes below threshold).
    """
    verifiable = [f for f in facts if f.source_excerpts and f.confidence >= 0.4]
    if not verifiable:
        logger.info("verification_skip — no verifiable facts")
        return facts

    verified_count = 0
    confirmed_count = 0
    weak_count = 0
    unsupported_count = 0

    for batch_start in range(0, len(verifiable), BATCH_SIZE):
        batch = verifiable[batch_start:batch_start + BATCH_SIZE]
        claim_blocks = []

        for i, fact in enumerate(batch):
            excerpt = fact.source_excerpts[0][:500] if fact.source_excerpts else ""
            claim_blocks.append(
                f"[{i}] Claim: {fact.claim}\n"
                f"    Evidence: {excerpt}\n"
                f"    Source: {fact.source_urls[0] if fact.source_urls else 'unknown'}"
            )

        system = (prompt_blocks or {}).get("instructions") or ""
        protocol = (prompt_blocks or {}).get("protocol") or ""
        prompt = PromptParts(
            system=system,
            variable=protocol.format(
                claim_blocks="\n\n".join(claim_blocks),
            ),
        )

        try:
            result = llm_call(
                prompt,
                max_tokens=2048,
                tier="fast",
                operation="org_research_verification",
                model_config=model_config,
            )
            parsed = parse_json_response(result.text)
        except Exception as e:
            logger.warning("verification_batch_failed batch=%d error=%s", batch_start, e)
            for fact in batch:
                fact.verification_status = "skipped"
            continue

        verifications = parsed.get("verifications", []) if isinstance(parsed, dict) else []

        verdict_map: dict[int, dict] = {}
        for v in verifications:
            if isinstance(v, dict) and "claim_index" in v:
                verdict_map[v["claim_index"]] = v

        for i, fact in enumerate(batch):
            v = verdict_map.get(i)
            if not v:
                fact.verification_status = "skipped"
                continue

            verdict = v.get("verdict", "").upper()
            verified_count += 1

            if verdict == "CONFIRMED":
                fact.verification_status = "confirmed"
                confirmed_count += 1
            elif verdict == "WEAK":
                fact.verification_status = "weak"
                fact.confidence *= CONFIDENCE_PENALTY_WEAK
                weak_count += 1
            elif verdict == "UNSUPPORTED":
                fact.verification_status = "unsupported"
                fact.confidence *= CONFIDENCE_PENALTY_UNSUPPORTED
                unsupported_count += 1
            else:
                fact.verification_status = "skipped"

    result_facts = [f for f in facts if f.verification_status != "unsupported"]

    logger.info(
        "verification_complete total=%d verified=%d confirmed=%d weak=%d unsupported=%d kept=%d",
        len(facts), verified_count, confirmed_count, weak_count,
        unsupported_count, len(result_facts),
    )
    return result_facts
