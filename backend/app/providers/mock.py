import json
from typing import Any

from app.providers.base import GenerationResult, ProviderExecutionError


class MockProvider:
    name = "mock"
    model_name = "deterministic-mock"

    def generate(
        self, input_data: dict[str, Any], *, expected_json: bool
    ) -> GenerationResult:
        if input_data.get("mock_error"):
            message = input_data["mock_error"]
            raise ProviderExecutionError(str(message))

        if "mock_output" in input_data:
            output = str(input_data["mock_output"])
        else:
            prompt = input_data.get("prompt", input_data)
            output = (
                json.dumps({"response": prompt}, sort_keys=True, ensure_ascii=False)
                if expected_json
                else prompt if isinstance(prompt, str) else json.dumps(
                    prompt, sort_keys=True, ensure_ascii=False
                )
            )
        return GenerationResult(
            output=output,
            provider=self.name,
            model_name=self.model_name,
        )
