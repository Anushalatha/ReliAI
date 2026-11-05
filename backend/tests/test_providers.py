import pytest
import httpx

from app.providers.base import ProviderExecutionError
from app.providers.groq import GroqProvider
from app.providers.mock import MockProvider
from app.providers.together import TogetherProvider
from app.providers import get_provider
from app.services.errors import InvalidProviderOutput, classify_execution_error


def test_mock_provider_is_deterministic():
    provider = MockProvider()

    first = provider.generate({"prompt": "hello"}, expected_json=False)
    second = provider.generate({"prompt": "hello"}, expected_json=False)

    assert first == second
    assert first.output == "hello"
    assert first.model_name == "deterministic-mock"


def test_mock_provider_returns_json_when_requested():
    result = MockProvider().generate({"prompt": "hello"}, expected_json=True)

    assert result.output == '{"response": "hello"}'


def test_mock_provider_can_return_a_controlled_case_failure():
    with pytest.raises(ProviderExecutionError, match="deliberate failure"):
        MockProvider().generate(
            {"prompt": "hello", "mock_error": "deliberate failure"},
            expected_json=False,
        )


def test_together_provider_sends_chat_request_and_records_usage():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "model": "Qwen/Qwen3.5-9B",
                "choices": [{"message": {"content": '{"answer":"hello"}'}}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 4},
            },
        )

    provider = TogetherProvider(
        api_key="test-key",
        model_name="Qwen/Qwen3.5-9B",
        transport=httpx.MockTransport(respond),
    )
    result = provider.generate({"prompt": "hello"}, expected_json=True)

    assert result.output == '{"answer":"hello"}'
    assert result.provider == "together"
    assert result.model_name == "Qwen/Qwen3.5-9B"
    assert result.input_tokens == 9
    assert result.output_tokens == 4
    request = requests[0]
    assert request.url == TogetherProvider.endpoint
    assert request.headers["Authorization"] == "Bearer test-key"
    assert request.read() == (
        b'{"model":"Qwen/Qwen3.5-9B","messages":'
        b'[{"role":"system","content":"Respond with valid JSON only."},'
        b'{"role":"user","content":"hello"}]}'
    )


@pytest.mark.parametrize(
    ("status_code", "message", "category"),
    [
        (401, "authentication failed", "provider_error"),
        (429, "rate limit", "rate_limit"),
        (503, "HTTP 503", "provider_error"),
    ],
)
def test_together_provider_classifies_http_errors(status_code, message, category):
    provider = TogetherProvider(
        api_key="test-key",
        model_name="Qwen/Qwen3.5-9B",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status_code, json={"error": "private body"})
        ),
    )

    with pytest.raises(ProviderExecutionError, match=message) as error:
        provider.generate({"prompt": "hello"}, expected_json=False)

    assert "private body" not in str(error.value)
    assert classify_execution_error(error.value) == category


def test_together_provider_handles_timeout_without_exposing_credentials():
    def timeout(request):
        raise httpx.ReadTimeout("request timed out")

    provider = TogetherProvider(
        api_key="private-test-key",
        model_name="Qwen/Qwen3.5-9B",
        transport=httpx.MockTransport(timeout),
    )

    with pytest.raises(ProviderExecutionError, match="timed out") as error:
        provider.generate({"prompt": "hello"}, expected_json=False)

    assert "private-test-key" not in str(error.value)
    assert classify_execution_error(error.value) == "timeout"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
    ],
)
def test_together_provider_rejects_malformed_responses(response):
    provider = TogetherProvider(
        api_key="test-key",
        model_name="Qwen/Qwen3.5-9B",
        transport=httpx.MockTransport(lambda request: response),
    )

    with pytest.raises(InvalidProviderOutput):
        provider.generate({"prompt": "hello"}, expected_json=False)


def test_together_provider_requires_api_key_without_fallback():
    provider = TogetherProvider(api_key=None, model_name="Qwen/Qwen3.5-9B")

    with pytest.raises(ProviderExecutionError, match="TOGETHER_API_KEY"):
        provider.generate({"prompt": "hello"}, expected_json=False)


def test_groq_provider_sends_chat_request_and_records_usage():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "model": "openai/gpt-oss-20b",
                "choices": [{"message": {"content": "hello from Groq"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 5},
            },
        )

    provider = GroqProvider(
        api_key="test-key",
        model_name="openai/gpt-oss-20b",
        transport=httpx.MockTransport(respond),
    )
    result = provider.generate({"prompt": "hello"}, expected_json=False)

    assert result.output == "hello from Groq"
    assert result.provider == "groq"
    assert result.model_name == "openai/gpt-oss-20b"
    assert result.input_tokens == 7
    assert result.output_tokens == 5
    request = requests[0]
    assert request.url == GroqProvider.endpoint
    assert request.headers["Authorization"] == "Bearer test-key"
    assert request.read() == (
        b'{"model":"openai/gpt-oss-20b","messages":'
        b'[{"role":"user","content":"hello"}]}'
    )


@pytest.mark.parametrize(
    ("status_code", "message", "category"),
    [
        (401, "authentication failed", "provider_error"),
        (429, "rate limit", "rate_limit"),
        (503, "HTTP 503", "provider_error"),
    ],
)
def test_groq_provider_classifies_http_errors(status_code, message, category):
    provider = GroqProvider(
        api_key="test-key",
        model_name="openai/gpt-oss-20b",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status_code, json={"error": "private body"})
        ),
    )

    with pytest.raises(ProviderExecutionError, match=message) as error:
        provider.generate({"prompt": "hello"}, expected_json=False)

    assert "private body" not in str(error.value)
    assert classify_execution_error(error.value) == category


def test_groq_provider_handles_timeout_without_exposing_credentials():
    def timeout(request):
        raise httpx.ReadTimeout("request timed out")

    provider = GroqProvider(
        api_key="private-test-key",
        model_name="openai/gpt-oss-20b",
        transport=httpx.MockTransport(timeout),
    )

    with pytest.raises(ProviderExecutionError, match="timed out") as error:
        provider.generate({"prompt": "hello"}, expected_json=False)

    assert "private-test-key" not in str(error.value)
    assert classify_execution_error(error.value) == "timeout"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
    ],
)
def test_groq_provider_rejects_malformed_responses(response):
    provider = GroqProvider(
        api_key="test-key",
        model_name="openai/gpt-oss-20b",
        transport=httpx.MockTransport(lambda request: response),
    )

    with pytest.raises(InvalidProviderOutput):
        provider.generate({"prompt": "hello"}, expected_json=False)


def test_groq_provider_requires_api_key_without_fallback():
    provider = GroqProvider(api_key=None, model_name="openai/gpt-oss-20b")

    with pytest.raises(ProviderExecutionError, match="GROQ_API_KEY"):
        provider.generate({"prompt": "hello"}, expected_json=False)


def test_groq_provider_is_registered_with_configured_settings(monkeypatch):
    from app.core.config import Settings

    settings = Settings(
        _env_file=None,
        groq_api_key="groq-test-key",
        groq_model="openai/gpt-oss-20b",
    )
    monkeypatch.setattr("app.providers.get_settings", lambda: settings)

    provider = get_provider("groq")

    assert isinstance(provider, GroqProvider)
    assert provider.api_key == "groq-test-key"
    assert provider.model_name == "openai/gpt-oss-20b"
