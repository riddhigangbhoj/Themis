from dataclasses import dataclass


@dataclass
class ModelConfig:
    id: str
    name: str
    provider: str
    max_output_tokens: int = 64000


MODELS: list[ModelConfig] = [
    ModelConfig(
        id="anthropic/claude-sonnet-4",
        name="Claude Sonnet 4",
        provider="Anthropic",
    ),
    ModelConfig(
        id="anthropic/claude-3.5-haiku",
        name="Claude 3.5 Haiku",
        provider="Anthropic",
    ),
    ModelConfig(
        id="openai/gpt-4o",
        name="GPT-4o",
        provider="OpenAI",
    ),
    ModelConfig(
        id="x-ai/grok-4.1-fast",
        name="Grok 4.1 Fast",
        provider="xAI",
        max_output_tokens=64000,
    ),
]


def get_model_config(model_id: str) -> ModelConfig | None:
    for model in MODELS:
        if model.id == model_id:
            return model
    return None
