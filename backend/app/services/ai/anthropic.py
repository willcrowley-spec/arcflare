from anthropic import AsyncAnthropic

from app.core.config import get_settings
from app.services.ai.base import BaseLLM


class AnthropicProvider(BaseLLM):
    """Anthropic Claude for reasoning. Embeddings are not supported — use Gemini."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY or None)
        self._model = "claude-3-5-sonnet-20241022"

    async def generate(self, prompt: str, *, max_tokens: int = 1024) -> str:
        msg = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        parts: list[str] = []
        for block in msg.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "".join(parts)

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError("Anthropic does not support embeddings; use Gemini embedding provider.")
