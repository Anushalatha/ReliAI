import uuid

import pytest

from app.models.evaluation import ExecutionTraceStatus
from app.providers.base import GenerationResult
from app.providers.mock import MockProvider
from app.services.errors import classify_execution_error, sanitize_error_message


def create_run(client, input_data, *, expected_json=False):
    dataset = client.post(
        "/datasets",
        json={
            "name": f"trace dataset {uuid.uuid4()}",
            "cases": [
                {
                    "name": "case",
                    "input_data": input_data,
                    "expected_output": "expected",
                    "expected_json": expected_json,
                }
            ],
        },
    )
    run = client.post("/runs", json={"dataset_id": dataset.json()["id"]})
    return dataset.json(), run.json()


def test_traces_persist_associations_duration_usage_and_api_results(client, monkeypatch):
    times = iter([100.0, 100.125])
    monkeypatch.setattr("app.services.evaluation.monotonic_time", lambda: next(times))
    dataset, run = create_run(client, {"prompt": "expected"})

    traces_response = client.get(f"/runs/{run['id']}/traces")
    trace = traces_response.json()[0]
    detail = client.get(f"/runs/{run['id']}/traces/{trace['id']}")

    assert traces_response.status_code == 200
    assert len(traces_response.json()) == 1
    assert trace["run_id"] == run["id"]
    assert trace["case_id"] == run["cases"][0]["id"]
    assert trace["operation_name"] == "evaluation.case"
    assert trace["status"] == ExecutionTraceStatus.SUCCEEDED.value
    assert trace["latency_ms"] == 125
    assert trace["input_tokens"] is None
    assert trace["output_tokens"] is None
    assert trace["request_id"]
    assert detail.status_code == 200
    assert detail.json()["id"] == trace["id"]
    assert client.get(f"/datasets/{dataset['id']}").status_code == 200


def test_trace_records_token_usage_only_when_provider_supplies_it(client, monkeypatch):
    def generate(self, input_data, *, expected_json):
        return GenerationResult(
            output="expected",
            provider="mock",
            model_name="mock-with-usage",
            input_tokens=12,
            output_tokens=4,
        )

    monkeypatch.setattr(MockProvider, "generate", generate)
    _, run = create_run(client, {"prompt": "expected"})
    trace = client.get(f"/runs/{run['id']}/traces").json()[0]

    assert trace["input_tokens"] == 12
    assert trace["output_tokens"] == 4
    assert trace["model_name"] == "mock-with-usage"


def test_failed_execution_trace_classifies_and_sanitizes_error(client):
    _, run = create_run(
        client,
        {"mock_error": "provider failed with api_key=sk-secret-value"},
    )
    trace = client.get(f"/runs/{run['id']}/traces").json()[0]

    assert run["status"] == "failed"
    assert trace["status"] == ExecutionTraceStatus.FAILED.value
    assert trace["error_type"] == "provider_error"
    assert "sk-secret-value" not in trace["error_message"]
    assert trace["error_details"] == {
        "category": "provider_error",
        "exception_type": "ProviderExecutionError",
    }


def test_invalid_json_output_is_quality_failure_not_execution_failure(client):
    _, run = create_run(
        client,
        {"mock_output": "not-json"},
        expected_json=True,
    )
    trace = client.get(f"/runs/{run['id']}/traces").json()[0]
    case = run["cases"][0]

    assert case["status"] == "completed"
    assert case["metrics"]["structured_output_valid"] == {
        "value": 0.0,
        "available": True,
    }
    assert trace["status"] == ExecutionTraceStatus.SUCCEEDED.value
    assert trace["error_type"] is None


def test_invalid_provider_result_is_classified_as_invalid_output(client, monkeypatch):
    monkeypatch.setattr(MockProvider, "generate", lambda *args, **kwargs: object())
    _, run = create_run(client, {"prompt": "hello"})
    trace = client.get(f"/runs/{run['id']}/traces").json()[0]

    assert run["status"] == "failed"
    assert trace["status"] == ExecutionTraceStatus.FAILED.value
    assert trace["error_type"] == "invalid_output"
    assert trace["error_details"]["category"] == "invalid_output"


def test_error_categories_cover_timeout_rate_limit_and_unknown():
    class RateLimitError(RuntimeError):
        pass

    assert classify_execution_error(TimeoutError("timeout")) == "timeout"
    assert classify_execution_error(RateLimitError("429")) == "rate_limit"
    assert classify_execution_error(RuntimeError("unexpected")) == "unknown_error"
    assert "secret" not in sanitize_error_message("Bearer secret")


def test_failed_trace_list_and_detail_report_missing_run_or_trace(client):
    run_id = uuid.uuid4()
    trace_id = uuid.uuid4()

    assert client.get(f"/runs/{run_id}/traces").status_code == 404
    assert client.get(f"/runs/{run_id}/traces/{trace_id}").status_code == 404
