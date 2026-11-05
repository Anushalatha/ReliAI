from app.core.config import get_settings
from app.providers.base import (
    GenerationResult,
    InvalidProviderOutput,
    Provider,
    ProviderExecutionError,
)
from app.providers.mock import MockProvider

PROVIDERS: dict[str, Provider] = {"mock": MockProvider()}


def get_provider(name: str, *, model_name: str | None = None) -> Provider:
    if name == "together":
        from app.providers.together import TogetherProvider

        settings = get_settings()
        return TogetherProvider(
            api_key=(
                settings.together_api_key.get_secret_value()
                if settings.together_api_key is not None
                else None
            ),
            model_name=model_name or settings.together_model,
        )
    if name == "groq":
        from app.providers.groq import GroqProvider

        settings = get_settings()
        return GroqProvider(
            api_key=(
                settings.groq_api_key.get_secret_value()
                if settings.groq_api_key is not None
                else None
            ),
            model_name=model_name or settings.groq_model,
        )
    try:
        return PROVIDERS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown provider: {name}") from exc


__all__ = [
    "GenerationResult",
    "InvalidProviderOutput",
    "MockProvider",
    "Provider",
    "ProviderExecutionError",
    "get_provider",
]
