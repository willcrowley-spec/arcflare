"""Multiplicative gate + additive refinement scoring for recommendation candidates.

Pure function — takes process enrichment data and returns a base_score.
No DB, no LLM, no side effects.
"""
from __future__ import annotations

AUTOMATION_POTENTIAL_MAP = {"low": 0.15, "medium": 0.5, "high": 0.9}
VALUE_CLASSIFICATION_MAP = {"NVA": 0.9, "BVA": 0.6, "VA": 0.3}
COMPLEXITY_MAP = {"low": 0.9, "medium": 0.6, "high": 0.3}

EVIDENCE_CAP = 15
TOUCHPOINT_CAP = 10
FAILURE_MODE_CAP = 8

GATE_WEIGHT = 0.6
REFINEMENT_WEIGHT = 0.4


def _evidence_strength(evidence_sources: list[dict]) -> float:
    if not evidence_sources:
        return 0.1
    confidences = [e.get("confidence", 0.5) for e in evidence_sources]
    avg_conf = sum(confidences) / len(confidences)
    count_norm = min(len(evidence_sources) / EVIDENCE_CAP, 1.0)
    return max(0.1, count_norm * avg_conf)


def _normalize_count(count: int, cap: int) -> float:
    return min(count / cap, 1.0) if cap > 0 else 0.0


def score_process(process: dict) -> dict:
    """Score a single process for automation potential.

    Args:
        process: dict with keys matching BusinessProcess columns
            (automation_potential, value_classification, complexity_score,
             evidence_sources, system_touchpoints, failure_modes)
            Plus 'has_handoff_gap': bool from linked ProcessHandoff data.

    Returns:
        dict with base_score, gate_score, refinement_score, and signal breakdown.
    """
    auto_pot = AUTOMATION_POTENTIAL_MAP.get(
        (process.get("automation_potential") or "").lower(), 0.4
    )
    evidence = _evidence_strength(process.get("evidence_sources", []))
    gate = auto_pot * evidence

    value_class = VALUE_CLASSIFICATION_MAP.get(
        (process.get("value_classification") or "").upper(), 0.5
    )
    complexity_inv = COMPLEXITY_MAP.get(
        (process.get("complexity_score") or "").lower(), 0.5
    )
    touchpoints = _normalize_count(
        len(process.get("system_touchpoints", [])), TOUCHPOINT_CAP
    )
    failure_risk = _normalize_count(
        len(process.get("failure_modes", [])), FAILURE_MODE_CAP
    )
    has_gap = 1.0 if process.get("has_handoff_gap") else 0.0

    refinement = (
        value_class * 0.30
        + complexity_inv * 0.25
        + touchpoints * 0.20
        + failure_risk * 0.15
        + has_gap * 0.10
    )

    base_score = round(gate * GATE_WEIGHT + refinement * REFINEMENT_WEIGHT, 4)
    base_score = max(0.0, min(1.0, base_score))

    return {
        "base_score": base_score,
        "gate_score": round(gate, 4),
        "refinement_score": round(refinement, 4),
        "signals": {
            "automation_potential": round(auto_pot, 2),
            "evidence_strength": round(evidence, 2),
            "value_classification": round(value_class, 2),
            "complexity_inverse": round(complexity_inv, 2),
            "system_touchpoints": round(touchpoints, 2),
            "failure_mode_risk": round(failure_risk, 2),
            "handoff_gap": round(has_gap, 2),
        },
    }


def score_synthesized(
    constituent_processes: list[dict],
    eliminated_handoff_count: int = 0,
) -> dict:
    """Score a synthesized (cross-process composite) candidate.

    Averages gate signals across constituent processes and adds a
    cross-process bonus based on eliminated handoffs.
    """
    if not constituent_processes:
        return {"base_score": 0.0, "gate_score": 0.0, "refinement_score": 0.0, "signals": {}}

    individual_scores = [score_process(p) for p in constituent_processes]

    avg_gate = sum(s["gate_score"] for s in individual_scores) / len(individual_scores)
    avg_refinement = sum(s["refinement_score"] for s in individual_scores) / len(individual_scores)

    cross_process_bonus = min(0.15, eliminated_handoff_count * 0.05)

    base_score = round(
        avg_gate * GATE_WEIGHT + (avg_refinement + cross_process_bonus) * REFINEMENT_WEIGHT,
        4,
    )
    base_score = max(0.0, min(1.0, base_score))

    avg_signals = {}
    if individual_scores:
        for key in individual_scores[0]["signals"]:
            avg_signals[key] = round(
                sum(s["signals"][key] for s in individual_scores) / len(individual_scores), 2
            )
        avg_signals["cross_process_bonus"] = round(cross_process_bonus, 2)

    return {
        "base_score": base_score,
        "gate_score": round(avg_gate, 4),
        "refinement_score": round(avg_refinement + cross_process_bonus, 4),
        "signals": avg_signals,
    }
