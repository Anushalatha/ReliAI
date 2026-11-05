import uuid

from fastapi.testclient import TestClient

from app.providers.base import GenerationResult, ProviderExecutionError
from app.services.benchmarking import percentile


class FixtureProvider:
    def __init__(self, name: str, *, fail: bool = False, model_name: str | None = None):
        self.name = name
        self.model_name = model_name or f"{name}-fixture-model"
        self.fail = fail

    def generate(self, input_data, *, expected_json):
        if self.fail:
            raise ProviderExecutionError("fixture provider unavailable")
        prompt = input_data.get("prompt", "")
        return GenerationResult(
            output=str(prompt),
            provider=self.name,
            model_name=self.model_name,
            input_tokens=10 if self.name == "groq" and prompt != "no usage" else None,
            output_tokens=5 if self.name == "groq" and prompt != "no usage" else None,
        )


def create_dataset(client: TestClient, cases=None):
    payload = {
        "name": f"benchmark dataset {uuid.uuid4()}",
        "cases": cases or [
            {
                "name": "measured",
                "input_data": {"prompt": "same"},
                "expected_output": "same",
                "reference_keywords": ["same", "not present"],
            },
            {"name": "unmeasured", "input_data": {"prompt": "also same"}},
        ],
    }
    response = client.post("/datasets", json=payload)
    assert response.status_code == 201
    return response.json()


def install_fixture_providers(monkeypatch, *, groq_fails=False):
    def factory(name: str, *, model_name: str | None = None):
        return FixtureProvider(
            name,
            fail=name == "groq" and groq_fails,
            model_name=model_name,
        )

    monkeypatch.setattr("app.services.evaluation.get_provider", factory)


def test_benchmark_persists_matched_provider_runs_and_metric_samples(client, monkeypatch):
    install_fixture_providers(monkeypatch)
    dataset = create_dataset(client)

    response = client.post(
        "/benchmarks",
        json={
            "dataset_id": dataset["id"],
            "providers": ["groq", "mock"],
            "groq_model": "groq-selected-model",
        },
    )

    assert response.status_code == 201
    benchmark = response.json()
    assert benchmark["status"] == "completed"
    assert benchmark["dataset_id"] == dataset["id"]
    assert benchmark["case_count"] == 2
    assert {result["provider"] for result in benchmark["results"]} == {"groq", "mock"}

    groq = next(result for result in benchmark["results"] if result["provider"] == "groq")
    mock = next(result for result in benchmark["results"] if result["provider"] == "mock")
    assert groq["models"] == ["groq-selected-model"]
    assert len(groq["run_ids"]) == 1
    assert groq["quality_metrics"]["exact_match"] == {"value": 1.0, "sample_count": 1}
    assert groq["quality_metrics"]["reference_keyword_coverage"] == {
        "value": 0.5,
        "sample_count": 1,
    }
    assert groq["input_tokens"] == {
        "average_tokens": 10.0,
        "total_tokens": 20,
        "sample_count": 2,
    }
    assert groq["latency"]["sample_count"] == 2
    assert groq["latency"]["p95_ms"] is None
    assert groq["case_outcomes"]["attempts"] == 2
    assert groq["case_outcomes"]["successes"] == 2
    assert mock["input_tokens"]["sample_count"] == 0
    assert mock["input_tokens"]["average_tokens"] is None

    persisted = client.get(f"/benchmarks/{benchmark['id']}")
    groq_run = client.get(f"/runs/{groq['run_ids'][0]}").json()
    mock_run = client.get(f"/runs/{mock['run_ids'][0]}").json()
    assert persisted.status_code == 200
    assert groq_run["dataset_id"] == dataset["id"]
    assert mock_run["dataset_id"] == dataset["id"]
    assert groq_run["benchmark_id"] == benchmark["id"]
    assert mock_run["benchmark_id"] == benchmark["id"]


def test_multi_case_benchmark_aggregates_only_available_metrics_and_usage(client, monkeypatch):
    install_fixture_providers(monkeypatch)
    dataset = create_dataset(
        client,
        cases=[
            {
                "name": "partial keyword coverage",
                "input_data": {"prompt": "exact"},
                "expected_output": "exact",
                "reference_keywords": ["exact", "missing"],
            },
            {
                "name": "mismatch and invalid JSON",
                "input_data": {"prompt": "not-json"},
                "expected_output": "expected",
                "expected_json": True,
                "reference_keywords": ["not-json"],
            },
            {"name": "no reference metrics or token usage", "input_data": {"prompt": "no usage"}},
        ],
    )

    response = client.post(
        "/benchmarks",
        json={"dataset_id": dataset["id"], "providers": ["groq"]},
    )

    assert response.status_code == 201
    result = response.json()["results"][0]
    assert result["quality_metrics"]["exact_match"] == {
        "value": 0.5,
        "sample_count": 2,
    }
    assert result["quality_metrics"]["structured_output_valid"] == {
        "value": 0.0,
        "sample_count": 1,
    }
    assert result["quality_metrics"]["reference_keyword_coverage"] == {
        "value": 0.75,
        "sample_count": 2,
    }
    assert result["latency"]["sample_count"] == 3
    assert result["latency"]["p95_ms"] is None
    assert result["input_tokens"] == {
        "average_tokens": 10.0,
        "total_tokens": 20,
        "sample_count": 2,
    }
    assert result["output_tokens"] == {
        "average_tokens": 5.0,
        "total_tokens": 10,
        "sample_count": 2,
    }


def test_partial_provider_failure_preserves_success_and_reports_failure(client, monkeypatch):
    install_fixture_providers(monkeypatch, groq_fails=True)
    dataset = create_dataset(client)

    benchmark = client.post(
        "/benchmarks",
        json={"dataset_id": dataset["id"], "providers": ["mock", "groq"]},
    ).json()

    assert benchmark["status"] == "partial"
    groq = next(result for result in benchmark["results"] if result["provider"] == "groq")
    mock = next(result for result in benchmark["results"] if result["provider"] == "mock")
    assert groq["run_outcomes"] == {"completed": 0, "failed": 1, "sample_count": 1}
    assert groq["case_outcomes"]["failures"] == 2
    assert groq["quality_metrics"]["exact_match"] == {"value": None, "sample_count": 0}
    assert groq["latency"]["sample_count"] == 2
    assert groq["input_tokens"] == {
        "average_tokens": None,
        "total_tokens": None,
        "sample_count": 0,
    }
    assert groq["error_counts"]["provider_error"] == 2
    assert mock["run_outcomes"] == {"completed": 1, "failed": 0, "sample_count": 1}
    assert mock["quality_metrics"]["exact_match"]["value"] == 1.0


def test_benchmark_handles_unknown_dataset_and_invalid_provider_request(client):
    missing = client.post(
        "/benchmarks",
        json={
            "dataset_id": str(uuid.uuid4()),
            "providers": ["mock", "groq"],
        },
    )
    duplicate = client.post(
        "/benchmarks",
        json={
            "dataset_id": str(uuid.uuid4()),
            "providers": ["mock", "mock"],
        },
    )
    unsupported = client.post(
        "/benchmarks",
        json={
            "dataset_id": str(uuid.uuid4()),
            "providers": ["mock", "together"],
        },
    )

    assert missing.status_code == 404
    assert duplicate.status_code == 422
    assert unsupported.status_code == 422


def test_benchmark_history_and_summary_are_persisted(client, monkeypatch):
    install_fixture_providers(monkeypatch)
    dataset = create_dataset(client)
    benchmark = client.post(
        "/benchmarks",
        json={"dataset_id": dataset["id"], "providers": ["mock", "groq"]},
    ).json()

    history = client.get("/benchmarks")
    summary = client.get("/benchmarks/summary")

    assert history.status_code == 200
    assert history.json()[0]["id"] == benchmark["id"]
    historical_detail = client.get(f"/benchmarks/{benchmark['id']}")
    assert historical_detail.status_code == 200
    assert historical_detail.json()["results"] == benchmark["results"]
    assert summary.status_code == 200
    assert {result["provider"] for result in summary.json()["provider_results"]} == {
        "mock",
        "groq",
    }
    assert summary.json()["recent_benchmarks"][0]["id"] == benchmark["id"]


def test_benchmark_percentile_uses_interpolated_measured_samples():
    assert percentile([10, 20, 30, 40], 0.5) == 25
    assert percentile([10, 20, 30, 40], 0.95) == 38.5
    assert percentile([], 0.95) is None


def test_benchmark_p95_available_only_at_minimum_sample_count(client, monkeypatch):
    install_fixture_providers(monkeypatch)
    cases = [
        {"name": f"case {index}", "input_data": {"prompt": "same"}}
        for index in range(20)
    ]
    dataset = create_dataset(client, cases=cases)

    benchmark = client.post(
        "/benchmarks",
        json={"dataset_id": dataset["id"], "providers": ["mock"]},
    ).json()

    result = benchmark["results"][0]
    assert result["latency"]["sample_count"] == 20
    assert result["latency"]["p95_ms"] is not None
    assert result["latency"]["p95_minimum_samples"] == 20
