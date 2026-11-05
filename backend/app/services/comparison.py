import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.evaluation import (
    EvaluationCase,
    EvaluationRun,
    ExecutionTrace,
)
from app.schemas import (
    CaseComparison,
    MetricComparison,
    RegressionFinding,
    RunComparisonResult,
)

HIGHER_IS_BETTER = {
    "exact_match",
    "structured_output_valid",
    "reference_keyword_coverage",
}
LOWER_IS_BETTER = {"latency_ms"}
SUPPORTED_METRICS = HIGHER_IS_BETTER | LOWER_IS_BETTER


def _metric_value(metrics: dict[str, Any] | None, key: str) -> float | None:
    if not metrics or key not in metrics:
        return None
    metric = metrics[key]
    if not isinstance(metric, dict) or not metric.get("available_cases", 0):
        return None
    value = metric.get("value")
    return float(value) if isinstance(value, (int, float)) else None


def _latency_value(traces: list[ExecutionTrace]) -> float | None:
    values = [trace.latency_ms for trace in traces if trace.latency_ms is not None]
    return sum(values) / len(values) if values else None


def _case_map(run: EvaluationRun) -> dict[uuid.UUID, EvaluationCase]:
    return {
        case.dataset_case_id: case
        for case in run.cases
        if case.dataset_case_id is not None
    }


def compare_runs(
    db: Session,
    *,
    previous_run_id: uuid.UUID,
    current_run_id: uuid.UUID,
    thresholds: dict[str, float],
) -> RunComparisonResult | None:
    runs = db.scalars(
        select(EvaluationRun)
        .where(EvaluationRun.id.in_([previous_run_id, current_run_id]))
        .options(selectinload(EvaluationRun.cases), selectinload(EvaluationRun.traces))
    ).all()
    run_by_id = {run.id: run for run in runs}
    previous = run_by_id.get(previous_run_id)
    current = run_by_id.get(current_run_id)
    if previous is None or current is None:
        return None

    reasons: list[str] = []
    if previous.id == current.id:
        reasons.append("A run cannot be compared with itself")
    if previous.dataset_id is None or previous.dataset_id != current.dataset_id:
        reasons.append("Runs do not reference the same dataset")

    previous_cases = _case_map(previous)
    current_cases = _case_map(current)
    if len(previous_cases) != len(previous.cases) or len(current_cases) != len(current.cases):
        reasons.append("One or both runs contain cases without dataset case identifiers")
    if previous_cases.keys() != current_cases.keys():
        reasons.append("Runs do not contain the same dataset cases")
    elif not reasons:
        for dataset_case_id in previous_cases:
            before = previous_cases[dataset_case_id]
            after = current_cases[dataset_case_id]
            if before.input_data != after.input_data or before.name != after.name:
                reasons.append(
                    f"Evaluation input changed for dataset case {dataset_case_id}"
                )
                break
            if (
                before.expected_output != after.expected_output
                or before.expected_json != after.expected_json
                or before.reference_keywords != after.reference_keywords
            ):
                reasons.append(
                    f"Metric definition changed for dataset case {dataset_case_id}"
                )
                break

    previous_metric_keys = set(previous.metrics or {})
    current_metric_keys = set(current.metrics or {})
    if (previous_metric_keys | current_metric_keys) - SUPPORTED_METRICS:
        reasons.append("Runs contain unsupported metric definitions")
    if previous_metric_keys != current_metric_keys:
        reasons.append("Runs contain different metric definitions")

    if reasons:
        return RunComparisonResult(
            status="incompatible",
            previous_run_id=previous.id,
            current_run_id=current.id,
            reasons=reasons,
        )

    metrics: list[MetricComparison] = []
    regressions: list[RegressionFinding] = []
    for metric_name in sorted(SUPPORTED_METRICS):
        previous_value = (
            _latency_value(previous.traces)
            if metric_name == "latency_ms"
            else _metric_value(previous.metrics, metric_name)
        )
        current_value = (
            _latency_value(current.traces)
            if metric_name == "latency_ms"
            else _metric_value(current.metrics, metric_name)
        )
        difference = (
            current_value - previous_value
            if previous_value is not None and current_value is not None
            else None
        )
        direction = (
            "higher_is_better" if metric_name in HIGHER_IS_BETTER else "lower_is_better"
        )
        metrics.append(
            MetricComparison(
                metric=metric_name,
                direction=direction,
                previous_value=previous_value,
                current_value=current_value,
                difference=difference,
                absolute_difference=abs(difference) if difference is not None else None,
                available=difference is not None,
            )
        )
        threshold = thresholds.get(metric_name)
        if threshold is None or difference is None:
            continue
        regression_amount = -difference if direction == "higher_is_better" else difference
        if regression_amount > threshold:
            regressions.append(
                RegressionFinding(
                    metric=metric_name,
                    previous_value=previous_value,
                    current_value=current_value,
                    difference=difference,
                    threshold=threshold,
                    direction=direction,
                )
            )

    case_comparisons = []
    for dataset_case_id in sorted(previous_cases, key=str):
        before = previous_cases[dataset_case_id]
        after = current_cases[dataset_case_id]
        score_difference = (
            after.score - before.score
            if before.score is not None and after.score is not None
            else None
        )
        case_comparisons.append(
            CaseComparison(
                dataset_case_id=dataset_case_id,
                name=after.name,
                previous_status=before.status,
                current_status=after.status,
                previous_score=before.score,
                current_score=after.score,
                score_difference=score_difference,
                output_changed=(
                    before.actual_output != after.actual_output
                    if before.actual_output is not None and after.actual_output is not None
                    else None
                ),
                newly_failed=before.status.value != "failed" and after.status.value == "failed",
                recovered=before.status.value == "failed" and after.status.value != "failed",
            )
        )

    return RunComparisonResult(
        status="compatible",
        previous_run_id=previous.id,
        current_run_id=current.id,
        metrics=metrics,
        cases=case_comparisons,
        regressions=regressions,
    )
