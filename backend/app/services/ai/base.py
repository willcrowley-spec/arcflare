from abc import ABC, abstractmethod


class BaseLLM(ABC):
    """Abstract provider for text generation and embeddings."""

    @abstractmethod
    async def generate(self, prompt: str, *, max_tokens: int = 1024) -> str:
        raise NotImplementedError

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError
