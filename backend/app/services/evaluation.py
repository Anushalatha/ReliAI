import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.evaluation import (
    EvaluationCase,
    EvaluationCaseStatus,
    EvaluationDataset,
    EvaluationRun,
    EvaluationRunStatus,
    ExecutionTrace,
    ExecutionTraceStatus,
)
from app.providers import get_provider
from app.providers.base import GenerationResult
from app.services.errors import (
    InvalidProviderOutput,
    classify_execution_error,
    sanitized_error_details,
    sanitize_error_message,
)
from app.services.metrics import aggregate_metrics, evaluate_metrics, unavailable_metrics

logger = logging.getLogger("reli.evaluation")
monotonic_time = time.perf_counter


def run_evaluation(
    db: Session,
    *,
    dataset_id: uuid.UUID,
    name: str | None,
    provider_name: str,
    request_id: str | None = None,
    benchmark_id: uuid.UUID | None = None,
    model_name: str | None = None,
) -> EvaluationRun | None:
    provider = (
        get_provider(provider_name)
        if model_name is None
        else get_provider(provider_name, model_name=model_name)
    )
    dataset = db.scalar(
        select(EvaluationDataset)
        .where(EvaluationDataset.id == dataset_id)
        .options(selectinload(EvaluationDataset.cases))
    )
    if dataset is None:
        return None

    started_at = datetime.now(timezone.utc)
    run = EvaluationRun(
        dataset_id=dataset.id,
        benchmark_id=benchmark_id,
        name=name or dataset.name,
        status=EvaluationRunStatus.RUNNING,
        provider=provider.name,
        model_name=provider.model_name,
        started_at=started_at,
    )
    db.add(run)
    db.flush()

    metrics_by_case: list[dict] = []
    failed_cases = 0
    for dataset_case in dataset.cases:
        case = EvaluationCase(
            run_id=run.id,
            dataset_case_id=dataset_case.id,
            name=dataset_case.name,
            status=EvaluationCaseStatus.RUNNING,
            input_data=dataset_case.input_data,
            expected_output=dataset_case.expected_output,
            expected_json=dataset_case.expected_json,
            reference_keywords=dataset_case.reference_keywords,
        )
        db.add(case)
        db.flush()
        trace_started_at = datetime.now(timezone.utc)
        monotonic_started = monotonic_time()
        trace = ExecutionTrace(
            run_id=run.id,
            case_id=case.id,
            request_id=request_id,
            operation_name="evaluation.case",
            status=ExecutionTraceStatus.RUNNING,
            provider=provider.name,
            model_name=provider.model_name,
            started_at=trace_started_at,
        )
        db.add(trace)
        db.flush()
        try:
            result = provider.generate(
                dataset_case.input_data,
                expected_json=dataset_case.expected_json,
            )
            if not isinstance(result, GenerationResult):
                raise InvalidProviderOutput("Provider returned an invalid result")
            if not isinstance(result.output, str):
                raise InvalidProviderOutput("Provider output must be a string")
            case.actual_output = result.output
            case.status = EvaluationCaseStatus.COMPLETED
            run.provider = result.provider
            run.model_name = result.model_name
            case.metrics = evaluate_metrics(
                result.output,
                expected_output=dataset_case.expected_output,
                expected_json=dataset_case.expected_json,
                reference_keywords=dataset_case.reference_keywords,
            )
            case.score = case.metrics["exact_match"]["value"]
            trace.status = ExecutionTraceStatus.SUCCEEDED
            trace.provider = result.provider
            trace.model_name = result.model_name
            trace.input_tokens = result.input_tokens
            trace.output_tokens = result.output_tokens
        except Exception as exc:
            category = classify_execution_error(exc)
            safe_message = sanitize_error_message(str(exc) or type(exc).__name__)
            logger.warning(
                "evaluation case failed",
                extra={
                    "run_id": str(run.id),
                    "case_id": str(case.id),
                    "error_type": category,
                    "error_message": safe_message,
                },
            )
            failed_cases += 1
            case.status = EvaluationCaseStatus.FAILED
            case.error_message = safe_message
            case.metrics = unavailable_metrics()
            trace.status = ExecutionTraceStatus.FAILED
            trace.error_type = category
            trace.error_message = safe_message
            trace.error_details = sanitized_error_details(exc, category)
        finally:
            trace.completed_at = datetime.now(timezone.utc)
            trace.latency_ms = max(
                0, round((monotonic_time() - monotonic_started) * 1000)
            )
        case.completed_at = datetime.now(timezone.utc)
        metrics_by_case.append(case.metrics)

    run.metrics = aggregate_metrics(metrics_by_case)
    run.status = EvaluationRunStatus.FAILED if failed_cases else EvaluationRunStatus.COMPLETED
    run.error_message = (
        f"{failed_cases} of {len(dataset.cases)} case(s) failed" if failed_cases else None
    )
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run
