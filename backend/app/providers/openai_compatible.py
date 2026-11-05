import json
from typing import Any

import httpx

from app.providers.base import (
    GenerationResult,
    InvalidProviderOutput,
    ProviderExecutionError,
)


class OpenAICompatibleChatProvider:
    name: str
    endpoint: str
    api_key_variable: str

    def __init__(
        self,
        *,
        api_key: str | None,
        model_name: str,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.timeout = timeout
        self.transport = transport

    def generate(
        self, input_data: dict[str, Any], *, expected_json: bool
    ) -> GenerationResult:
        if not self.api_key:
            raise ProviderExecutionError(
                f"{self.name} is selected but {self.api_key_variable} is not configured"
            )

        prompt = input_data.get("prompt", input_data)
        content = prompt if isinstance(prompt, str) else json.dumps(
            prompt, sort_keys=True, ensure_ascii=False
        )
        messages = []
        if expected_json:
            messages.append(
                {
                    "role": "system",
                    "content": "Respond with valid JSON only.",
                }
            )
        messages.append({"role": "user", "content": content})

        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model_name, "messages": messages},
                )
        except httpx.TimeoutException as exc:
            raise ProviderExecutionError(f"{self.name} request timed out") from exc
        except httpx.RequestError as exc:
            raise ProviderExecutionError(f"{self.name} request failed") from exc

        if response.status_code in (401, 403):
            raise ProviderExecutionError(
                f"{self.name} authentication failed (HTTP {response.status_code})"
            )
        if response.status_code == 429:
            raise ProviderExecutionError(
                f"{self.name} rate limit exceeded (HTTP 429)"
            )
        if response.is_error:
            raise ProviderExecutionError(
                f"{self.name} request failed (HTTP {response.status_code})"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise InvalidProviderOutput(
                f"{self.name} returned a malformed JSON response"
            ) from exc
        if not isinstance(payload, dict):
            raise InvalidProviderOutput(f"{self.name} returned a malformed response")

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise InvalidProviderOutput(f"{self.name} returned no completion choices")
        message = choices[0].get("message")
        output = message.get("content") if isinstance(message, dict) else None
        if not isinstance(output, str):
            raise InvalidProviderOutput(f"{self.name} returned a malformed completion")

        response_model = payload.get("model")
        model_name = (
            response_model
            if isinstance(response_model, str) and response_model
            else self.model_name
        )
        usage = payload.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        return GenerationResult(
            output=output,
            provider=self.name,
            model_name=model_name,
            input_tokens=self._token_count(usage.get("prompt_tokens")),
            output_tokens=self._token_count(usage.get("completion_tokens")),
        )

    @staticmethod
    def _token_count(value: object) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return None
