from app.services.ai.anthropic import AnthropicProvider
from app.services.ai.base import BaseLLM
from app.services.ai.openai import OpenAIProvider


def get_embedding_provider() -> BaseLLM:
    """Prefer OpenAI for embeddings."""
    return OpenAIProvider()


def get_reasoning_provider() -> BaseLLM:
    """Prefer Anthropic for long-form reasoning."""
    return AnthropicProvider()
