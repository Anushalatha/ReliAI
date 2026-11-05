import math
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.evaluation import (
    Benchmark,
    BenchmarkStatus,
    EvaluationCase,
    EvaluationCaseStatus,
    EvaluationDataset,
    EvaluationRun,
    EvaluationRunStatus,
    ExecutionTrace,
    ExecutionTraceStatus,
)
from app.services.evaluation import run_evaluation

QUALITY_METRICS = (
    "exact_match",
    "structured_output_valid",
    "reference_keyword_coverage",
)
P95_MINIMUM_SAMPLES = 20
ERROR_CATEGORIES = (
    "timeout",
    "authentication",
    "rate_limit",
    "provider_error",
    "invalid_output",
    "unknown_error",
)


def percentile(values: list[int], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def run_benchmark(
    db: Session,
    *,
    dataset_id: uuid.UUID,
    name: str | None,
    providers: list[str],
    groq_model: str | None,
    request_id: str | None = None,
) -> Benchmark | None:
    dataset = db.scalar(
        select(EvaluationDataset)
        .where(EvaluationDataset.id == dataset_id)
        .options(selectinload(EvaluationDataset.cases))
    )
    if dataset is None:
        return None

    benchmark = Benchmark(
        dataset_id=dataset.id,
        name=name or dataset.name,
        status=BenchmarkStatus.RUNNING,
        providers=providers,
    )
    db.add(benchmark)
    db.commit()
    db.refresh(benchmark)

    for provider_name in providers:
        run_evaluation(
            db,
            dataset_id=dataset.id,
            name=f"{benchmark.name} · {provider_name}",
            provider_name=provider_name,
            request_id=request_id,
            benchmark_id=benchmark.id,
            model_name=groq_model if provider_name == "groq" else None,
        )

    runs = list(
        db.scalars(
            select(EvaluationRun).where(EvaluationRun.benchmark_id == benchmark.id)
        ).all()
    )
    completed = sum(run.status == EvaluationRunStatus.COMPLETED for run in runs)
    failed = sum(run.status == EvaluationRunStatus.FAILED for run in runs)
    if completed == len(providers):
        benchmark.status = BenchmarkStatus.COMPLETED
    elif completed:
        benchmark.status = BenchmarkStatus.PARTIAL
    else:
        benchmark.status = BenchmarkStatus.FAILED
    if completed + failed != len(providers):
        benchmark.status = BenchmarkStatus.PARTIAL if completed else BenchmarkStatus.FAILED
    benchmark.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(benchmark)
    return benchmark


def provider_result(db: Session, runs: list[EvaluationRun]) -> dict[str, Any]:
    runs = sorted(runs, key=lambda run: (run.created_at, str(run.id)))
    run_ids = [run.id for run in runs]
    cases = list(
        db.scalars(
            select(EvaluationCase)
            .where(EvaluationCase.run_id.in_(run_ids))
            .order_by(EvaluationCase.created_at, EvaluationCase.id)
        ).all()
    ) if run_ids else []
    traces = list(
        db.scalars(
            select(ExecutionTrace)
            .where(ExecutionTrace.run_id.in_(run_ids))
            .order_by(ExecutionTrace.started_at, ExecutionTrace.id)
        ).all()
    ) if run_ids else []

    provider = next((run.provider for run in runs if run.provider), "unknown")
    models = sorted({run.model_name for run in runs if run.model_name})
    quality_metrics: dict[str, dict[str, int | float | None]] = {}
    for metric_name in QUALITY_METRICS:
        values = []
        for case in cases:
            metric = (case.metrics or {}).get(metric_name)
            if (
                isinstance(metric, dict)
                and metric.get("available") is True
                and isinstance(metric.get("value"), (float, int))
                and not isinstance(metric.get("value"), bool)
            ):
                values.append(float(metric["value"]))
        quality_metrics[metric_name] = {
            "value": sum(values) / len(values) if values else None,
            "sample_count": len(values),
        }

    latency_values = [
        trace.latency_ms
        for trace in traces
        if trace.latency_ms is not None and trace.latency_ms >= 0
    ]
    input_tokens = [trace.input_tokens for trace in traces if trace.input_tokens is not None]
    output_tokens = [
        trace.output_tokens for trace in traces if trace.output_tokens is not None
    ]
    attempted_cases = [
        case
        for case in cases
        if case.status in (EvaluationCaseStatus.COMPLETED, EvaluationCaseStatus.FAILED)
    ]
    successful_cases = sum(
        case.status == EvaluationCaseStatus.COMPLETED for case in attempted_cases
    )
    failed_cases = sum(case.status == EvaluationCaseStatus.FAILED for case in attempted_cases)
    run_completed = sum(run.status == EvaluationRunStatus.COMPLETED for run in runs)
    run_failed = sum(run.status == EvaluationRunStatus.FAILED for run in runs)

    errors = {category: 0 for category in ERROR_CATEGORIES}
    for trace in traces:
        if trace.status != ExecutionTraceStatus.FAILED:
            continue
        error_type = (trace.error_type or "").casefold()
        error_message = (trace.error_message or "").casefold()
        if error_type == "timeout":
            category = "timeout"
        elif error_type == "rate_limit":
            category = "rate_limit"
        elif "authentication failed" in error_message:
            category = "authentication"
        elif error_type == "invalid_output":
            category = "invalid_output"
        elif error_type == "provider_error":
            category = "provider_error"
        else:
            category = "unknown_error"
        errors[category] += 1

    def token_summary(values: list[int]) -> dict[str, int | float | None]:
        return {
            "average_tokens": sum(values) / len(values) if values else None,
            "total_tokens": sum(values) if values else None,
            "sample_count": len(values),
        }

    return {
        "provider": provider,
        "models": models,
        "run_ids": run_ids,
        "run_outcomes": {
            "completed": run_completed,
            "failed": run_failed,
            "sample_count": run_completed + run_failed,
        },
        "quality_metrics": quality_metrics,
        "latency": {
            "average_ms": sum(latency_values) / len(latency_values) if latency_values else None,
            "median_ms": percentile(latency_values, 0.5),
            "p50_ms": percentile(latency_values, 0.5),
            "p95_ms": (
                percentile(latency_values, 0.95)
                if len(latency_values) >= P95_MINIMUM_SAMPLES
                else None
            ),
            "sample_count": len(latency_values),
            "p95_minimum_samples": P95_MINIMUM_SAMPLES,
        },
        "input_tokens": token_summary(input_tokens),
        "output_tokens": token_summary(output_tokens),
        "case_outcomes": {
            "attempts": len(attempted_cases),
            "successes": successful_cases,
            "failures": failed_cases,
            "success_rate": (
                successful_cases / len(attempted_cases) if attempted_cases else None
            ),
            "failure_rate": failed_cases / len(attempted_cases) if attempted_cases else None,
            "sample_count": len(attempted_cases),
        },
        "error_counts": errors,
    }


def benchmark_detail(db: Session, benchmark_id: uuid.UUID) -> dict[str, Any] | None:
    benchmark = db.scalar(
        select(Benchmark)
        .where(Benchmark.id == benchmark_id)
        .options(selectinload(Benchmark.dataset).selectinload(EvaluationDataset.cases))
    )
    if benchmark is None:
        return None
    runs = list(
        db.scalars(
            select(EvaluationRun)
            .where(EvaluationRun.benchmark_id == benchmark.id)
            .order_by(EvaluationRun.created_at, EvaluationRun.id)
        ).all()
    )
    grouped: dict[str, list[EvaluationRun]] = defaultdict(list)
    for run in runs:
        grouped[run.provider or "unknown"].append(run)
    results = [provider_result(db, grouped[key]) for key in benchmark.providers if key in grouped]
    return {
        "id": benchmark.id,
        "dataset_id": benchmark.dataset_id,
        "dataset_name": benchmark.dataset.name if benchmark.dataset else None,
        "case_count": len(benchmark.dataset.cases) if benchmark.dataset else 0,
        "name": benchmark.name,
        "status": benchmark.status,
        "providers": benchmark.providers,
        "created_at": benchmark.created_at,
        "completed_at": benchmark.completed_at,
        "results": results,
    }


def benchmark_summary(db: Session, limit: int = 30) -> dict[str, Any]:
    benchmarks = list(
        db.scalars(
            select(Benchmark)
            .order_by(Benchmark.created_at.desc(), Benchmark.id)
            .limit(limit)
        ).all()
    )
    benchmark_ids = [benchmark.id for benchmark in benchmarks]
    runs = list(
        db.scalars(
            select(EvaluationRun)
            .where(EvaluationRun.benchmark_id.in_(benchmark_ids))
            .order_by(EvaluationRun.created_at, EvaluationRun.id)
        ).all()
    ) if benchmark_ids else []
    grouped: dict[str, list[EvaluationRun]] = defaultdict(list)
    for run in runs:
        grouped[run.provider or "unknown"].append(run)
    return {
        "provider_results": [
            provider_result(db, grouped[provider])
            for provider in sorted(grouped)
        ],
        "recent_benchmarks": [
            {
                "id": benchmark.id,
                "dataset_id": benchmark.dataset_id,
                "name": benchmark.name,
                "status": benchmark.status,
                "providers": benchmark.providers,
                "created_at": benchmark.created_at,
                "completed_at": benchmark.completed_at,
            }
            for benchmark in benchmarks
        ],
    }
