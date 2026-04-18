"""Adaptive token-aware rate limiter for LLM API calls.

Tracks BOTH input and output tokens against separate per-minute ceilings
read from provider response headers.  Anthropic Tier 1 limits:
  - 30-40K input tokens/min
  - 8K output tokens/min  <-- the real bottleneck

When the tier upgrades the limiter auto-detects the new ceiling from
the next response's headers.  Zero config changes needed.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

logger = logging.getLogger(__name__)

_DEFAULT_INPUT_TPM = 25_000
_DEFAULT_OUTPUT_TPM = 6_000   # conservative vs Tier 1's 8K
_WINDOW_SECONDS = 60


class _SlidingWindow:
    """Sliding 60-second token counter."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._entries: deque[tuple[float, int]] = deque()

    @property
    def limit(self) -> int:
        return self._limit

    @limit.setter
    def limit(self, value: int) -> None:
        self._limit = value

    def _purge(self) -> None:
        cutoff = time.monotonic() - _WINDOW_SECONDS
        while self._entries and self._entries[0][0] < cutoff:
            self._entries.popleft()

    def total(self) -> int:
        self._purge()
        return sum(t for _, t in self._entries)

    def headroom(self) -> int:
        return max(0, self._limit - self.total())

    def record(self, tokens: int) -> None:
        self._entries.append((time.monotonic(), tokens))

    def earliest_expiry(self) -> float:
        """Seconds until the oldest entry expires from the window."""
        if not self._entries:
            return 0.0
        return max(0.0, (self._entries[0][0] + _WINDOW_SECONDS) - time.monotonic())


class AdaptiveTokenRateLimiter:
    """Dual-window (input + output) rate limiter with auto-detection.

    Usage (async)::

        limiter = get_limiter(model)
        await limiter.acquire(estimated_input_tokens, estimated_output_tokens)
        response = litellm.completion(...)
        limiter.update_from_response(response, actual_output_tokens)
    """

    def __init__(
        self,
        default_input_tpm: int = _DEFAULT_INPUT_TPM,
        default_output_tpm: int = _DEFAULT_OUTPUT_TPM,
    ) -> None:
        self._lock = asyncio.Lock()
        self._input = _SlidingWindow(default_input_tpm)
        self._output = _SlidingWindow(default_output_tpm)
        self._detected = False

    async def acquire(self, est_input: int, est_output: int = 0) -> None:
        """Wait until both input and output windows have room."""
        while True:
            async with self._lock:
                in_ok = est_input <= self._input.headroom()
                out_ok = (est_output <= 0) or (est_output <= self._output.headroom())
                if in_ok and out_ok:
                    self._input.record(est_input)
                    if est_output > 0:
                        self._output.record(est_output)
                    return

            sleep_for = max(
                self._input.earliest_expiry(),
                self._output.earliest_expiry(),
                0.5,
            )
            sleep_for = min(sleep_for + 0.1, 15.0)

            logger.debug(
                "rate_limiter_waiting in=%d/%d out=%d/%d sleep=%.1fs",
                self._input.total(), self._input.limit,
                self._output.total(), self._output.limit,
                sleep_for,
            )
            await asyncio.sleep(sleep_for)

    def record_output(self, actual_output_tokens: int) -> None:
        """Record actual output tokens after a call completes.

        Call this to true-up the output window with actual token counts
        vs the estimate passed to ``acquire()``.
        """
        if actual_output_tokens > 0:
            self._output.record(actual_output_tokens)

    def update_from_response(self, response: object) -> None:
        """Read rate-limit headers from a LiteLLM response and update ceilings."""
        headers = getattr(response, "response_headers", None) or {}
        if not headers:
            hidden = getattr(response, "_hidden_params", None) or {}
            headers = hidden.get("additional_headers", {}) or {}

        self._try_update_limit(
            headers, "x-ratelimit-limit-input-tokens", self._input, "input",
        )
        self._try_update_limit(
            headers, "x-ratelimit-limit-output-tokens", self._output, "output",
        )
        # Anthropic also sends a combined "tokens" header
        combined = (
            headers.get("x-ratelimit-limit-tokens")
            or headers.get("x_ratelimit_limit_tokens")
        )
        if combined is not None and not self._detected:
            try:
                val = int(combined)
                if val > 0 and val != self._input.limit:
                    old = self._input.limit
                    self._input.limit = val
                    self._detected = True
                    logger.info("rate_limiter_input_updated old=%d new=%d", old, val)
            except (ValueError, TypeError):
                pass

    def _try_update_limit(
        self, headers: dict, key: str, window: _SlidingWindow, label: str,
    ) -> None:
        raw = headers.get(key) or headers.get(key.replace("-", "_"))
        if raw is None:
            return
        try:
            val = int(raw)
            if val > 0 and val != window.limit:
                old = window.limit
                window.limit = val
                self._detected = True
                logger.info("rate_limiter_%s_updated old=%d new=%d", label, old, val)
        except (ValueError, TypeError):
            pass


_limiters: dict[str, AdaptiveTokenRateLimiter] = {}


def get_limiter(model: str) -> AdaptiveTokenRateLimiter:
    """Return the rate limiter for the given model's provider."""
    provider = model.split("/")[0] if "/" in model else "default"
    if provider not in _limiters:
        _limiters[provider] = AdaptiveTokenRateLimiter()
        logger.info(
            "rate_limiter_created provider=%s input_tpm=%d output_tpm=%d",
            provider, _DEFAULT_INPUT_TPM, _DEFAULT_OUTPUT_TPM,
        )
    return _limiters[provider]
