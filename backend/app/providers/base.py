from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class GenerationResult:
    output: str
    provider: str
    model_name: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class ProviderExecutionError(RuntimeError):
    pass


class InvalidProviderOutput(ValueError):
    pass


class Provider(Protocol):
    name: str
    model_name: str

    def generate(
        self, input_data: dict[str, Any], *, expected_json: bool
    ) -> GenerationResult: ...
