from openai import AsyncOpenAI

from app.core.config import get_settings
from app.services.ai.base import BaseLLM


class OpenAIProvider(BaseLLM):
    """OpenAI-backed embeddings (and optional generation)."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY or None)
        self._embed_model = "text-embedding-3-large"

    async def generate(self, prompt: str, *, max_tokens: int = 1024) -> str:
        resp = await self._client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        choice = resp.choices[0]
        return choice.message.content or ""

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.embeddings.create(model=self._embed_model, input=text)
        return list(resp.data[0].embedding)
