"""Unified LLM interface powered by LiteLLM.

Usage:
    from app.services.ai.router import llm_call, parse_json_response

    result = llm_call("Analyze this text...", max_tokens=1000, tier="fast")
    data = parse_json_response(result.text)

LiteLLM handles provider dispatch based on the model prefix:
    - anthropic/claude-* -> Anthropic API
    - gemini/*           -> Google Gemini API
    - openai/*           -> OpenAI API
"""
import json
import logging
import time
from dataclasses import dataclass
from typing import Literal

import litellm

from app.core.config import get_settings

logger = logging.getLogger(__name__)

litellm.drop_params = True
litellm.return_response_headers = True


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


def _resolve_model(
    tier: Literal["lite", "fast", "strong"],
    operation: str | None = None,
    model_config: dict | None = None,
) -> str:
    """Resolve a LiteLLM model string via: org override -> op default -> tier default."""
    from app.services.ai.operations import resolve_model
    return resolve_model(operation=operation, model_config=model_config, tier=tier)


def llm_call(
    prompt: str,
    max_tokens: int = 1000,
    tier: Literal["lite", "fast", "strong"] = "fast",
    operation: str | None = None,
    model_config: dict | None = None,
) -> LLMResult:
    """Make an LLM call using LiteLLM with automatic provider routing.

    Args:
        operation: Named operation (e.g. "discovery_synthesis") for model resolution.
        model_config: Org analysis_config dict containing optional model_overrides.
    """
    model = _resolve_model(tier, operation=operation, model_config=model_config)

    from app.core.observability import langfuse_generation
    from app.services.ai.operations import get_output_format, get_thinking_budget
    from app.services.ai.response_schemas import get_response_schema

    with langfuse_generation(
        name=operation or "llm_call",
        model=model,
        input=prompt,
        metadata={"tier": tier, "max_tokens": max_tokens, "operation": operation},
    ) as gen:
        start_time = time.time()

        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }

        schema = get_response_schema(operation)
        output_fmt = get_output_format(operation)
        if schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": operation or "response",
                    "strict": True,
                    "schema": schema,
                },
            }
        elif output_fmt == "json":
            kwargs["response_format"] = {"type": "json_object"}

        thinking_budget = get_thinking_budget(operation)
        if thinking_budget > 0:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
            kwargs["max_tokens"] = max(kwargs["max_tokens"], thinking_budget + 1024)

        response = litellm.completion(**kwargs)

        text = response.choices[0].message.content or ""
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        from app.services.ai.rate_limiter import get_limiter
        try:
            limiter = get_limiter(model)
            limiter.update_from_response(response)
            limiter.record_output(output_tokens)
        except Exception:
            pass

        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000

        cost = response._hidden_params.get("response_cost") if hasattr(response, "_hidden_params") else None

        if gen is not None:
            try:
                cost_details = None
                if cost is not None and cost > 0:
                    input_cost = litellm.cost_per_token(model=model, prompt_tokens=input_tokens, completion_tokens=0)
                    output_cost = litellm.cost_per_token(model=model, prompt_tokens=0, completion_tokens=output_tokens)
                    cost_details = {
                        "input": input_cost[0] if isinstance(input_cost, tuple) else input_cost,
                        "output": output_cost[1] if isinstance(output_cost, tuple) else output_cost,
                    }
                gen.update(
                    output=text,
                    usage_details={"input": input_tokens, "output": output_tokens},
                    cost_details=cost_details,
                )
            except Exception:
                logger.debug("langfuse_generation_update_failed model=%s", model)

    provider = model.split("/")[0] if "/" in model else "unknown"

    logger.info(
        "llm_call model=%s tier=%s in=%d out=%d cost=$%.4f dur=%.0fms",
        model, tier, input_tokens, output_tokens, cost or 0, duration_ms,
    )

    return LLMResult(
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
        provider=provider,
    )


@dataclass
class ChatStreamChunk:
    """A single chunk from a streaming chat response."""
    type: Literal["text", "function_call", "done", "error"]
    text: str = ""
    function_name: str = ""
    function_args: dict | None = None
    function_call_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


def stream_chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    max_tokens: int = 4096,
    operation: str = "chat",
    model_config: dict | None = None,
):
    """Streaming LLM call with function calling via LiteLLM.

    Yields ``ChatStreamChunk`` objects: text deltas, function_call proposals, and a
    final ``done`` chunk with token counts.

    Args:
        messages: List of {"role": ..., "content": ...} dicts.
        tools: OpenAI-format tool definitions from ``get_openai_tools()``.
        max_tokens: Max output tokens.
        operation: Operation name for model resolution.
        model_config: Org analysis_config for overrides.
    """
    from app.services.ai.operations import get_default_tier

    tier = get_default_tier(operation)
    model = _resolve_model(tier, operation=operation, model_config=model_config)

    try:
        response = litellm.completion(
            model=model,
            messages=messages,
            tools=tools if tools else None,
            max_tokens=max_tokens,
            stream=True,
        )

        text_buffer = ""
        tool_calls_buffer: dict[int, dict] = {}
        total_in = 0
        total_out = 0

        for chunk in response:
            if hasattr(chunk, "usage") and chunk.usage:
                total_in = getattr(chunk.usage, "prompt_tokens", 0) or 0
                total_out = getattr(chunk.usage, "completion_tokens", 0) or 0

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            if delta.content:
                text_buffer += delta.content
                yield ChatStreamChunk(type="text", text=delta.content, model=model)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {
                            "id": tc.id or "",
                            "name": "",
                            "args_str": "",
                        }
                    if tc.function:
                        if tc.function.name:
                            tool_calls_buffer[idx]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_calls_buffer[idx]["args_str"] += tc.function.arguments

            if chunk.choices[0].finish_reason:
                break

        for idx, tc_data in sorted(tool_calls_buffer.items()):
            args = {}
            try:
                args = json.loads(tc_data["args_str"]) if tc_data["args_str"] else {}
            except json.JSONDecodeError:
                logger.warning("tool_call_args_parse_failed name=%s", tc_data["name"])

            yield ChatStreamChunk(
                type="function_call",
                function_name=tc_data["name"],
                function_args=args,
                function_call_id=tc_data["id"] or f"{tc_data['name']}_{idx}",
                model=model,
            )

        yield ChatStreamChunk(
            type="done", model=model,
            input_tokens=total_in, output_tokens=total_out,
        )
    except Exception as exc:
        logger.exception("stream_chat_with_tools_failed model=%s", model)
        yield ChatStreamChunk(type="error", text=str(exc), model=model)


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
