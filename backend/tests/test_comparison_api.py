import uuid

from app.models.evaluation import EvaluationRun, ExecutionTrace, ExecutionTraceStatus
from app.providers.base import GenerationResult
from app.providers.mock import MockProvider


def create_dataset(client):
    response = client.post(
        "/datasets",
        json={
            "name": f"comparison {uuid.uuid4()}",
            "cases": [
                {
                    "name": "exact",
                    "input_data": {"prompt": "unused"},
                    "expected_output": "pass",
                },
                {
                    "name": "unscored",
                    "input_data": {"prompt": "other"},
                },
            ],
        },
    )
    assert response.status_code == 201
    return response.json()


def run_with_output(client, dataset_id, output):
    response = client.post("/runs", json={"dataset_id": dataset_id})
    assert response.status_code == 201
    return response.json()


def test_comparison_reports_differences_case_changes_and_regressions(client, monkeypatch):
    outputs = iter(["pass", "same", "fail", "changed"])

    def generate(self, input_data, *, expected_json):
        return GenerationResult(
            output=next(outputs),
            provider="mock",
            model_name="deterministic-mock",
        )

    monkeypatch.setattr(MockProvider, "generate", generate)
    dataset = create_dataset(client)
    previous = run_with_output(client, dataset["id"], "unused")
    current = run_with_output(client, dataset["id"], "unused")

    response = client.post(
        "/runs/compare",
        json={
            "previous_run_id": previous["id"],
            "current_run_id": current["id"],
            "thresholds": {"exact_match": 0.25},
        },
    )
    result = response.json()

    assert response.status_code == 200
    assert result["status"] == "compatible"
    exact_match = next(metric for metric in result["metrics"] if metric["metric"] == "exact_match")
    assert exact_match["previous_value"] == 1.0
    assert exact_match["current_value"] == 0.0
    assert exact_match["difference"] == -1.0
    assert exact_match["absolute_difference"] == 1.0
    assert result["regressions"] == [
        {
            "metric": "exact_match",
            "previous_value": 1.0,
            "current_value": 0.0,
            "difference": -1.0,
            "threshold": 0.25,
            "direction": "higher_is_better",
        }
    ]
    exact_case = next(case for case in result["cases"] if case["name"] == "exact")
    assert exact_case["score_difference"] == -1.0
    assert exact_case["output_changed"] is True


def test_comparison_detects_newly_failed_and_recovered_cases(client, monkeypatch):
    outcomes = iter(["pass", "fail", "fail", "pass"])

    def generate(self, input_data, *, expected_json):
        output = next(outcomes)
        if output == "fail":
            raise RuntimeError("execution failed")
        return GenerationResult(output, "mock", "deterministic-mock")

    monkeypatch.setattr(MockProvider, "generate", generate)
    dataset = create_dataset(client)
    previous = run_with_output(client, dataset["id"], "ignored")
    current = run_with_output(client, dataset["id"], "ignored")

    result = client.post(
        "/runs/compare",
        json={
            "previous_run_id": previous["id"],
            "current_run_id": current["id"],
        },
    ).json()

    assert result["status"] == "compatible"
    exact_case = next(case for case in result["cases"] if case["name"] == "exact")
    unscored_case = next(case for case in result["cases"] if case["name"] == "unscored")
    assert exact_case["newly_failed"] is True
    assert unscored_case["recovered"] is True


def test_incompatible_dataset_runs_are_not_compared(client):
    first = create_dataset(client)
    second = create_dataset(client)
    previous = run_with_output(client, first["id"], "unused")
    current = run_with_output(client, second["id"], "unused")

    result = client.post(
        "/runs/compare",
        json={
            "previous_run_id": previous["id"],
            "current_run_id": current["id"],
        },
    ).json()

    assert result["status"] == "incompatible"
    assert result["metrics"] == []
    assert "Runs do not reference the same dataset" in result["reasons"]


def test_changed_case_metric_definition_is_not_compared(client, db_session):
    from app.models.evaluation import EvaluationCase

    dataset = create_dataset(client)
    previous = run_with_output(client, dataset["id"], "unused")
    current = run_with_output(client, dataset["id"], "unused")
    case = (
        db_session.query(EvaluationCase)
        .filter_by(run_id=uuid.UUID(current["id"]), name="exact")
        .one()
    )
    case.expected_output = "changed definition"
    db_session.commit()

    result = client.post(
        "/runs/compare",
        json={
            "previous_run_id": previous["id"],
            "current_run_id": current["id"],
        },
    ).json()

    assert result["status"] == "incompatible"
    assert any("Metric definition changed" in reason for reason in result["reasons"])


def test_missing_metric_is_unavailable_without_regression(client, database):
    dataset = create_dataset(client)
    previous = run_with_output(client, dataset["id"], "ignored")
    current = run_with_output(client, dataset["id"], "ignored")
    with database() as db:
        previous_run = db.get(EvaluationRun, uuid.UUID(previous["id"]))
        previous_run.metrics = {
            **previous_run.metrics,
            "exact_match": {
            "value": None,
            "available_cases": 0,
            "total_cases": 2,
            },
        }
        db.commit()

    result = client.post(
        "/runs/compare",
        json={
            "previous_run_id": previous["id"],
            "current_run_id": current["id"],
            "thresholds": {"exact_match": 0.0},
        },
    ).json()
    exact = next(metric for metric in result["metrics"] if metric["metric"] == "exact_match")

    assert exact["available"] is False
    assert exact["previous_value"] is None
    assert all(finding["metric"] != "exact_match" for finding in result["regressions"])


def test_lower_is_better_metric_flags_latency_regression(client, database):
    dataset = create_dataset(client)
    previous = run_with_output(client, dataset["id"], "ignored")
    current = run_with_output(client, dataset["id"], "ignored")
    with database() as db:
        before = db.query(ExecutionTrace).filter_by(run_id=uuid.UUID(previous["id"])).all()
        after = db.query(ExecutionTrace).filter_by(run_id=uuid.UUID(current["id"])).all()
        for trace in before:
            trace.latency_ms = 20
        for trace in after:
            trace.latency_ms = 80
            trace.status = ExecutionTraceStatus.SUCCEEDED
        db.commit()

    response = client.post(
        f"/runs/{current['id']}/regressions",
        json={"baseline_run_id": previous["id"], "thresholds": {"latency_ms": 25}},
    )
    result = response.json()

    assert response.status_code == 200
    assert result["status"] == "compatible"
    assert result["regressions"] == [
        {
            "metric": "latency_ms",
            "previous_value": 20.0,
            "current_value": 80.0,
            "difference": 60.0,
            "threshold": 25.0,
            "direction": "lower_is_better",
        }
    ]


def test_comparison_api_validates_thresholds_and_missing_runs(client):
    invalid = client.post(
        "/runs/compare",
        json={
            "previous_run_id": str(uuid.uuid4()),
            "current_run_id": str(uuid.uuid4()),
            "thresholds": {"made_up": 0.1},
        },
    )
    missing = client.post(
        "/runs/compare",
        json={
            "previous_run_id": str(uuid.uuid4()),
            "current_run_id": str(uuid.uuid4()),
        },
    )

    assert invalid.status_code == 422
    assert missing.status_code == 404
