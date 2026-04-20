"""Adaptive token-aware rate limiter for LLM API calls.

Gates on INPUT tokens per minute using a sliding 60-second window.
Output token limits are handled reactively via 429 backoff in the
retry layer -- pre-booking output tokens causes deadlock when many
parallel calls queue against Tier 1's tiny 8K output/min ceiling.

The input ceiling auto-detects from Anthropic response headers.
When the tier upgrades, the next response updates the limit automatically.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

logger = logging.getLogger(__name__)

_DEFAULT_INPUT_TPM = 25_000  # conservative vs Anthropic Tier 1's ~30-38K

_PROVIDER_DEFAULTS: dict[str, int] = {
    "anthropic": 25_000,
    "gemini": 4_000_000,
    "openai": 200_000,
}
_WINDOW_SECONDS = 60


class AdaptiveTokenRateLimiter:
    """Sliding-window input-token rate limiter with header auto-detection.

    Usage (async)::

        limiter = get_limiter(model)
        await limiter.acquire(estimated_input_tokens)
        response = litellm.completion(...)
        limiter.update_from_response(response)
    """

    def __init__(self, default_tpm: int = _DEFAULT_INPUT_TPM) -> None:
        self._lock = asyncio.Lock()
        self._window: deque[tuple[float, int]] = deque()
        self._tpm: int = default_tpm
        self._detected = False

    @property
    def tokens_per_minute(self) -> int:
        return self._tpm

    def _purge(self) -> None:
        cutoff = time.monotonic() - _WINDOW_SECONDS
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()

    def _total(self) -> int:
        self._purge()
        return sum(t for _, t in self._window)

    def _headroom(self) -> int:
        return max(0, self._tpm - self._total())

    async def acquire(self, estimated_tokens: int) -> None:
        """Wait until the sliding window has room for ``estimated_tokens``.

        If a single request exceeds the per-minute limit but the window
        is empty, it's allowed through (it'll be the only call that minute).
        This prevents oversized prompts from deadlocking the pipeline.
        """
        while True:
            async with self._lock:
                current = self._total()
                fits = estimated_tokens <= (self._tpm - current)
                window_empty = current == 0

                if fits or window_empty:
                    self._window.append((time.monotonic(), estimated_tokens))
                    if not fits:
                        logger.warning(
                            "rate_limiter_oversized est=%d limit=%d (window empty, allowing)",
                            estimated_tokens, self._tpm,
                        )
                    return

            sleep_for = 2.0
            if self._window:
                oldest = self._window[0][0]
                expires_in = (oldest + _WINDOW_SECONDS) - time.monotonic()
                sleep_for = max(1.0, min(expires_in + 0.5, 30.0))

            logger.debug(
                "rate_limiter_waiting est=%d used=%d/%d sleep=%.1fs",
                estimated_tokens, self._total(), self._tpm, sleep_for,
            )
            await asyncio.sleep(sleep_for)

    def update_from_response(self, response: object) -> None:
        """Read rate-limit headers from a LiteLLM response and update the ceiling."""
        headers = getattr(response, "response_headers", None) or {}
        if not headers:
            hidden = getattr(response, "_hidden_params", None) or {}
            headers = hidden.get("additional_headers", {}) or {}

        for key in (
            "x-ratelimit-limit-input-tokens",
            "x_ratelimit_limit_input_tokens",
            "x-ratelimit-limit-tokens",
            "x_ratelimit_limit_tokens",
        ):
            raw = headers.get(key)
            if raw is not None:
                try:
                    val = int(raw)
                    if val > 0 and val != self._tpm:
                        old = self._tpm
                        self._tpm = val
                        self._detected = True
                        logger.info("rate_limiter_updated old_tpm=%d new_tpm=%d", old, val)
                    elif not self._detected:
                        self._detected = True
                    return
                except (ValueError, TypeError):
                    pass


_limiters: dict[str, AdaptiveTokenRateLimiter] = {}


def get_limiter(model: str) -> AdaptiveTokenRateLimiter:
    """Return the rate limiter for the given model's provider."""
    from app.services.ai.router import _provider_from_model
    provider = _provider_from_model(model)
    if provider not in _limiters:
        default = _PROVIDER_DEFAULTS.get(provider, _DEFAULT_INPUT_TPM)
        _limiters[provider] = AdaptiveTokenRateLimiter(default_tpm=default)
        logger.info("rate_limiter_created provider=%s default_tpm=%d", provider, default)
    return _limiters[provider]
