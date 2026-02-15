from openai import AsyncOpenAI

from backend.config import OPENROUTER_API_KEY

_client: AsyncOpenAI | None = None


def get_openrouter_client() -> AsyncOpenAI:
    global _client
    if _client is not None:
        return _client

    _client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )
    return _client
