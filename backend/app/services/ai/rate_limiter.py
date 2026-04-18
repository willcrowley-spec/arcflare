"""Adaptive token-aware rate limiter for LLM API calls.

Reads provider rate-limit headers from LiteLLM responses to auto-detect
the org's actual token-per-minute ceiling.  No hardcoded limits -- when
the Anthropic tier upgrades, the limiter picks up the new ceiling from
the next response's headers automatically.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

logger = logging.getLogger(__name__)

_DEFAULT_TPM = 25_000  # conservative default for Anthropic Tier 1 (actual: 30K)
_WINDOW_SECONDS = 60


class AdaptiveTokenRateLimiter:
    """Sliding-window token rate limiter that auto-adapts from response headers.

    Usage (async)::

        limiter = AdaptiveTokenRateLimiter()
        await limiter.acquire(estimated_input_tokens)
        response = litellm.completion(...)
        limiter.update_from_response(response)
    """

    def __init__(self, default_tpm: int = _DEFAULT_TPM) -> None:
        self._lock = asyncio.Lock()
        self._window: deque[tuple[float, int]] = deque()
        self._tpm: int = default_tpm
        self._detected = False

    @property
    def tokens_per_minute(self) -> int:
        return self._tpm

    def _purge_expired(self) -> None:
        cutoff = time.monotonic() - _WINDOW_SECONDS
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()

    def _window_total(self) -> int:
        self._purge_expired()
        return sum(t for _, t in self._window)

    async def acquire(self, estimated_tokens: int) -> None:
        """Wait until the sliding window has room for ``estimated_tokens``."""
        while True:
            async with self._lock:
                current = self._window_total()
                headroom = self._tpm - current
                if estimated_tokens <= headroom:
                    self._window.append((time.monotonic(), estimated_tokens))
                    return

            sleep_for = 1.0
            if self._window:
                oldest_ts = self._window[0][0]
                expires_in = (oldest_ts + _WINDOW_SECONDS) - time.monotonic()
                sleep_for = max(0.5, min(expires_in + 0.1, 10.0))

            logger.debug(
                "rate_limiter_waiting tokens=%d current=%d limit=%d sleep=%.1fs",
                estimated_tokens, self._window_total(), self._tpm, sleep_for,
            )
            await asyncio.sleep(sleep_for)

    def update_from_response(self, response: object) -> None:
        """Read rate-limit headers from a LiteLLM response and update the ceiling."""
        headers = getattr(response, "response_headers", None) or {}
        if not headers:
            hidden = getattr(response, "_hidden_params", None) or {}
            headers = hidden.get("additional_headers", {}) or {}

        limit_raw = (
            headers.get("x-ratelimit-limit-tokens")
            or headers.get("x_ratelimit_limit_tokens")
        )
        if limit_raw is not None:
            try:
                detected = int(limit_raw)
                if detected > 0 and detected != self._tpm:
                    old = self._tpm
                    self._tpm = detected
                    self._detected = True
                    logger.info(
                        "rate_limiter_updated old_tpm=%d new_tpm=%d", old, detected,
                    )
                elif not self._detected:
                    self._detected = True
            except (ValueError, TypeError):
                pass


# Module-level singleton keyed by provider prefix
_limiters: dict[str, AdaptiveTokenRateLimiter] = {}


def get_limiter(model: str) -> AdaptiveTokenRateLimiter:
    """Return the rate limiter for the given model's provider.

    Creates one per provider on first access (e.g. ``anthropic``, ``gemini``).
    """
    provider = model.split("/")[0] if "/" in model else "default"
    if provider not in _limiters:
        _limiters[provider] = AdaptiveTokenRateLimiter()
        logger.info("rate_limiter_created provider=%s default_tpm=%d", provider, _DEFAULT_TPM)
    return _limiters[provider]
