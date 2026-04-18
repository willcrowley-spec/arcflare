"""Model pricing table for Langfuse cost tracking (USD per token)."""
from __future__ import annotations

MODEL_PRICES: dict[str, dict[str, float]] = {
    "gemini-2.5-pro": {"input": 1.25e-6, "output": 10.0e-6},
    "gemini-2.5-flash": {"input": 0.15e-6, "output": 0.60e-6},
    "gemini-2.0-flash": {"input": 0.10e-6, "output": 0.40e-6},
    "gemini-embedding-2-preview": {"input": 0.006e-6, "output": 0.0},
}


def compute_cost(
    model: str, input_tokens: int, output_tokens: int
) -> dict[str, float] | None:
    """Return ``{"input": ..., "output": ...}`` in USD, or None if model unknown."""
    prices = MODEL_PRICES.get(model)
    if not prices:
        return None
    return {
        "input": input_tokens * prices["input"],
        "output": output_tokens * prices["output"],
    }
