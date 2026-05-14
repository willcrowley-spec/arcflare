from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover - exercised only in lean local envs
    from difflib import SequenceMatcher

    class _FallbackFuzz:
        @staticmethod
        def token_sort_ratio(left: str, right: str) -> float:
            left_tokens = " ".join(sorted(str(left or "").split()))
            right_tokens = " ".join(sorted(str(right or "").split()))
            return SequenceMatcher(None, left_tokens, right_tokens).ratio() * 100

    fuzz = _FallbackFuzz()

_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_WORD_RE = re.compile(r"[^A-Za-z0-9]+")
_CUSTOM_SUFFIX_RE = re.compile(r"__(?:c|mdt|x|e|b)$", re.IGNORECASE)
_NOISE_WORDS = {
    "custom",
    "object",
    "objects",
    "record",
    "records",
    "salesforce",
    "sobject",
    "sobjects",
}
_BUSINESS_OBJECT_HINTS = {
    "agreement": ("Contract",),
    "pricing": ("PricebookEntry",),
    "price": ("PricebookEntry",),
    "pricebook": ("PricebookEntry",),
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _split_words(value: str) -> list[str]:
    spaced = _CAMEL_BOUNDARY_RE.sub(" ", value.replace("_", " "))
    return [w for w in _NON_WORD_RE.sub(" ", spaced).lower().split() if w]


def normalize_object_text(value: object) -> str:
    """Normalize human/API object references for conservative matching."""
    raw = _text(value)
    raw = _CUSTOM_SUFFIX_RE.sub("", raw)
    words = [w for w in _split_words(raw) if w not in _NOISE_WORDS]
    if words and words[-1] == "c":
        words = words[:-1]
    return " ".join(words)


def _object_refs(metadata_objects: Iterable[dict]) -> list[dict]:
    refs: list[dict] = []
    for item in metadata_objects:
        if not isinstance(item, dict):
            continue
        api_name = _text(item.get("api_name"))
        if not api_name:
            continue
        label = _text(item.get("label")) or api_name
        aliases = {
            normalize_object_text(api_name),
            normalize_object_text(label),
            normalize_object_text(api_name.replace("__c", "").replace("__mdt", "")),
        }
        aliases = {a for a in aliases if a}
        refs.append({"api_name": api_name, "label": label, "aliases": sorted(aliases)})
    return refs


def _mapped(raw: str, ref: dict, *, confidence: float, method: str) -> dict:
    return {
        "raw": raw,
        "status": "resolved",
        "api_name": ref["api_name"],
        "label": ref["label"],
        "confidence": round(confidence, 3),
        "match_method": method,
    }


def _unresolved(raw: str, *, status: str, reason: str, candidates: list[dict] | None = None) -> dict:
    row = {
        "raw": raw,
        "status": status,
        "reason": reason,
    }
    if candidates:
        row["candidates"] = candidates[:3]
    return row


def _contained_alias_matches(raw: str, normalized: str, refs: list[dict]) -> list[dict]:
    raw_tokens = set(normalized.split())
    by_api: dict[str, dict] = {}
    for ref in refs:
        for alias in ref["aliases"]:
            alias_tokens = set(alias.split())
            if not alias_tokens or not alias_tokens.issubset(raw_tokens):
                continue
            existing = by_api.get(ref["api_name"])
            if existing is None or len(alias_tokens) > len(existing["tokens"]):
                by_api[ref["api_name"]] = {"ref": ref, "tokens": alias_tokens}

    specific_matches = []
    matches = list(by_api.values())
    for match in matches:
        tokens = match["tokens"]
        if any(tokens < other["tokens"] for other in matches):
            continue
        specific_matches.append(match)

    return [
        _mapped(
            raw,
            match["ref"],
            confidence=min(0.99, 0.93 + (len(match["tokens"]) * 0.02)),
            method="contained_alias",
        )
        for match in sorted(specific_matches, key=lambda m: (-len(m["tokens"]), m["ref"]["api_name"]))
    ]


def _hint_matches(raw: str, normalized: str, refs: list[dict], mapped_api_names: set[str]) -> list[dict]:
    raw_tokens = set(normalized.split())
    refs_by_api = {ref["api_name"].lower(): ref for ref in refs}
    matches = []
    for token in raw_tokens:
        for api_name in _BUSINESS_OBJECT_HINTS.get(token, ()):
            if api_name in mapped_api_names:
                continue
            ref = refs_by_api.get(api_name.lower())
            if ref is not None:
                mapped_api_names.add(api_name)
                matches.append(_mapped(raw, ref, confidence=0.9, method=f"business_hint:{token}"))
    return matches


def resolve_object_references(
    raw_values: Iterable[object],
    metadata_objects: Iterable[dict],
    *,
    fuzzy_threshold: float = 0.9,
    ambiguity_margin: float = 0.05,
) -> dict:
    """Resolve recommendation object language to known Salesforce object API names.

    This intentionally prefers unresolved blockers over risky guesses. Only exact,
    normalized, or high-confidence non-ambiguous fuzzy matches become API names.
    """
    refs = _object_refs(metadata_objects)
    exact_api = {ref["api_name"].lower(): ref for ref in refs}
    alias_index: dict[str, list[dict]] = defaultdict(list)
    for ref in refs:
        for alias in ref["aliases"]:
            alias_index[alias].append(ref)

    mapped: list[dict] = []
    unresolved: list[dict] = []
    warnings: list[str] = []
    seen_raw: set[str] = set()

    for value in raw_values:
        raw = _text(value)
        if not raw or raw in seen_raw:
            continue
        seen_raw.add(raw)

        exact = exact_api.get(raw.lower())
        if exact:
            row = _mapped(raw, exact, confidence=1.0, method="api_name_exact")
            mapped.append(row)
            continue

        normalized = normalize_object_text(raw)
        if not normalized:
            unresolved.append(_unresolved(raw, status="unresolved", reason="empty_after_normalization"))
            continue

        exact_aliases = alias_index.get(normalized, [])
        exact_alias_api_names = sorted({ref["api_name"] for ref in exact_aliases})
        if len(exact_alias_api_names) == 1:
            ref = exact_aliases[0]
            row = _mapped(raw, ref, confidence=0.98, method="normalized_exact")
            mapped.append(row)
            continue
        if len(exact_alias_api_names) > 1:
            unresolved.append(
                _unresolved(
                    raw,
                    status="ambiguous",
                    reason="multiple_exact_metadata_matches",
                    candidates=[
                        {"api_name": ref["api_name"], "label": ref["label"], "confidence": 0.98}
                        for ref in exact_aliases
                    ],
                )
            )
            continue

        contained_matches = _contained_alias_matches(raw, normalized, refs)
        hinted_matches = _hint_matches(
            raw,
            normalized,
            refs,
            {row["api_name"] for row in contained_matches},
        )
        if contained_matches or hinted_matches:
            mapped.extend(contained_matches)
            mapped.extend(hinted_matches)
            continue

        candidates: list[tuple[float, dict]] = []
        for ref in refs:
            score = max((fuzz.token_sort_ratio(normalized, alias) / 100 for alias in ref["aliases"]), default=0.0)
            candidates.append((score, ref))
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        best_score, best_ref = candidates[0] if candidates else (0.0, {})
        next_distinct_score = next(
            (score for score, ref in candidates[1:] if ref.get("api_name") != best_ref.get("api_name")),
            0.0,
        )
        candidate_rows = [
            {"api_name": ref["api_name"], "label": ref["label"], "confidence": round(score, 3)}
            for score, ref in candidates
            if score > 0
        ]
        if best_score >= fuzzy_threshold and (best_score - next_distinct_score) >= ambiguity_margin:
            row = _mapped(raw, best_ref, confidence=best_score, method="fuzzy")
            mapped.append(row)
        elif best_score >= 0.7 and (best_score - next_distinct_score) < ambiguity_margin:
            unresolved.append(
                _unresolved(raw, status="ambiguous", reason="close_fuzzy_metadata_matches", candidates=candidate_rows)
            )
        else:
            unresolved.append(
                _unresolved(raw, status="unresolved", reason="no_confident_metadata_match", candidates=candidate_rows)
            )

    deduped_mapped = []
    seen_rows: set[tuple[str, str]] = set()
    for row in mapped:
        key = (row["raw"], row["api_name"])
        if key in seen_rows:
            continue
        seen_rows.add(key)
        deduped_mapped.append(row)

    if unresolved:
        warnings.append("Some recommendation data requirements could not be mapped to Salesforce metadata.")

    return {"mapped": deduped_mapped, "unresolved": unresolved, "warnings": warnings}


def score_text_against_resolved_object(text: object, resolved_object: dict) -> float:
    normalized_text = normalize_object_text(text)
    aliases = [
        normalize_object_text(resolved_object.get("api_name")),
        normalize_object_text(resolved_object.get("label")),
        normalize_object_text(resolved_object.get("raw")),
    ]
    aliases = [a for a in aliases if a]
    if not normalized_text or not aliases:
        return 0.0
    text_tokens = set(normalized_text.split())
    scores = []
    for alias in aliases:
        alias_tokens = set(alias.split())
        if alias_tokens and alias_tokens.issubset(text_tokens):
            scores.append(1.0)
        else:
            scores.append(fuzz.token_sort_ratio(normalized_text, alias) / 100)
    return max(scores, default=0.0)
