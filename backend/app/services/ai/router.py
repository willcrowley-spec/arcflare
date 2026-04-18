"""Unified LLM interface -- provider-agnostic wrapper for all AI calls.

Usage:
    from app.services.ai.router import llm_call, parse_json_response

    result = llm_call("Analyze this text...", max_tokens=1000, tier="fast")
    data = parse_json_response(result.text)

Tiers:
    - lite: cheapest/fastest, for bulk tasks like object descriptions
    - fast: balanced, for entity extraction and matching
    - strong: most capable, for synthesis and complex analysis
"""
import json
import time
import logging
from dataclasses import dataclass
from typing import Literal

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_last_call_time: float = 0.0
_openai_client = None
_anthropic_client = None
_gemini_client = None


@dataclass
class LLMResult:
    """Response from an LLM call."""
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str


def get_embedding_provider():
    """Return the configured Gemini client for embeddings."""
    settings = get_settings()
    key = (settings.GEMINI_API_KEY or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required for embeddings")
    from google import genai
    return genai.Client(api_key=key)


def get_reasoning_provider():
    """Return the configured reasoning/chat provider."""
    settings = get_settings()
    provider = getattr(settings, "LLM_PROVIDER", "anthropic")
    if provider == "anthropic":
        key = (settings.ANTHROPIC_API_KEY or "").strip()
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY required")
        from anthropic import Anthropic
        return Anthropic(api_key=key)
    elif provider == "openai":
        key = (settings.OPENAI_API_KEY or "").strip()
        if not key:
            raise RuntimeError("OPENAI_API_KEY required")
        from openai import OpenAI
        return OpenAI(api_key=key)
    raise RuntimeError(f"Unknown LLM_PROVIDER: {provider}")


PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "anthropic": {"lite": "claude-3-haiku-20240307", "fast": "claude-sonnet-4-20250514", "strong": "claude-opus-4-20250514"},
    "openai": {"lite": "gpt-4o-mini", "fast": "gpt-4o", "strong": "gpt-4o"},
    "gemini": {"lite": "gemini-2.0-flash-lite", "fast": "gemini-2.5-flash", "strong": "gemini-2.5-pro"},
}


def _resolve_model(
    tier: Literal["lite", "fast", "strong"],
    operation: str | None = None,
    model_config: dict | None = None,
) -> tuple[str, str]:
    """Resolve (provider, model) via: operation override -> env var -> hardcoded default."""
    from app.services.ai.operations import resolve_model_for_operation

    override = resolve_model_for_operation(operation, model_config, tier)
    if override:
        return override

    settings = get_settings()
    provider = getattr(settings, "LLM_PROVIDER", "anthropic")

    model_map = {
        "lite": getattr(settings, "LLM_LITE_MODEL", None),
        "fast": getattr(settings, "LLM_FAST_MODEL", None),
        "strong": getattr(settings, "LLM_STRONG_MODEL", None),
    }

    model = model_map.get(tier)

    if not model:
        model = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["anthropic"])[tier]

    return provider, model


def llm_call(
    prompt: str,
    max_tokens: int = 1000,
    tier: Literal["lite", "fast", "strong"] = "fast",
    operation: str | None = None,
    model_config: dict | None = None,
) -> LLMResult:
    """Make an LLM call using the configured provider and tier.

    Args:
        operation: Named operation (e.g. "discovery_synthesis") for org-level overrides.
        model_config: Org analysis_config dict containing optional model_overrides.
    """
    global _last_call_time

    provider, model = _resolve_model(tier, operation=operation, model_config=model_config)

    settings = get_settings()
    rate_delay = float(getattr(settings, "LLM_RATE_DELAY", 0))
    if rate_delay > 0:
        elapsed = time.time() - _last_call_time
        if elapsed < rate_delay:
            time.sleep(rate_delay - elapsed)

    _last_call_time = time.time()

    from app.core.observability import langfuse_generation

    with langfuse_generation(
        name=operation or "llm_call",
        model=model,
        input=prompt,
        metadata={"provider": provider, "tier": tier, "max_tokens": max_tokens, "operation": operation},
    ) as gen:
        start_time = time.time()

        if provider == "gemini":
            result = _call_gemini(prompt, max_tokens, model, operation=operation)
        elif provider == "anthropic":
            result = _call_anthropic(prompt, max_tokens, model)
        elif provider == "openai":
            result = _call_openai(prompt, max_tokens, model)
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000

        if gen is not None:
            try:
                gen.update(
                    output=result.text,
                    usage={
                        "input": result.input_tokens,
                        "output": result.output_tokens,
                        "total": result.input_tokens + result.output_tokens,
                    },
                )
            except Exception:
                logger.debug("langfuse_generation_update_failed model=%s", model)

    logger.info(
        "llm_call provider=%s model=%s tier=%s in=%d out=%d dur=%.0fms",
        provider, model, tier, result.input_tokens, result.output_tokens, duration_ms,
    )

    return result


def parse_json_response(text: str | None) -> dict | list:
    """Parse a JSON response, stripping markdown code fences if present."""
    if not text:
        raise ValueError("Empty LLM response — nothing to parse")
    raw = text.strip()

    if raw.startswith("```"):
        parts = raw.split("```")
        for part in parts[1:]:
            cleaned = part.strip()
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith("{") or cleaned.startswith("["):
                raw = cleaned
                break

    return json.loads(raw)


def _call_anthropic(prompt: str, max_tokens: int, model: str) -> LLMResult:
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import Anthropic
        settings = get_settings()
        _anthropic_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    response = _anthropic_client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return LLMResult(
        text=response.content[0].text,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        model=model,
        provider="anthropic",
    )


def _call_openai(prompt: str, max_tokens: int, model: str) -> LLMResult:
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        settings = get_settings()
        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)

    response = _openai_client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    choice = response.choices[0]
    usage = response.usage
    return LLMResult(
        text=choice.message.content or "",
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
        model=model,
        provider="openai",
    )


def _build_gemini_config(max_tokens: int, model: str, operation: str | None = None):
    """Build a GenerateContentConfig with per-operation thinking budget.

    Gemini 2.5 models: ``max_output_tokens`` is the TOTAL budget for
    thinking + response.  The thinking budget is pulled from the operations
    registry so each pipeline stage gets an appropriate allocation.
    """
    from app.services.ai.operations import get_thinking_budget

    thinking = get_thinking_budget(operation)
    supports_thinking = "2.5-pro" in model or "2.5-flash" in model

    try:
        from google.genai import types

        kwargs: dict = {"max_output_tokens": max_tokens}
        if supports_thinking and thinking > 0:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking)
            kwargs["max_output_tokens"] = max_tokens + thinking
        elif supports_thinking:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        else:
            kwargs["temperature"] = 0
        return types.GenerateContentConfig(**kwargs)
    except Exception as exc:
        logger.debug("gemini_typed_config_failed model=%s error=%s, falling back to plain dict", model, exc)
        config: dict = {"max_output_tokens": max_tokens}
        if not supports_thinking:
            config["temperature"] = 0
        return config


def _call_gemini(
    prompt: str, max_tokens: int, model: str, operation: str | None = None,
) -> LLMResult:
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        settings = get_settings()
        api_key = getattr(settings, "GEMINI_API_KEY", "")
        _gemini_client = genai.Client(api_key=api_key)

    config = _build_gemini_config(max_tokens, model, operation=operation)

    response = _gemini_client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )

    text = response.text
    if text is None:
        parts = []
        try:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "thought") and part.thought:
                    continue
                if part.text:
                    parts.append(part.text)
        except (IndexError, AttributeError):
            pass
        text = "".join(parts) if parts else ""
        if not text:
            logger.warning(
                "gemini_empty_response model=%s finish=%s",
                model,
                getattr(response.candidates[0], "finish_reason", "unknown") if response.candidates else "no_candidates",
            )

    usage = response.usage_metadata
    return LLMResult(
        text=text,
        input_tokens=getattr(usage, "prompt_token_count", 0) or 0 if usage else 0,
        output_tokens=getattr(usage, "candidates_token_count", 0) or 0 if usage else 0,
        model=model,
        provider="gemini",
    )
