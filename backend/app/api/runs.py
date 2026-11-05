import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import get_db
from app.models.evaluation import EvaluationCase, EvaluationRun, ExecutionTrace
from app.schemas import (
    CompareRunsRequest,
    EvaluationCaseRead,
    EvaluationRunDetail,
    EvaluationRunRead,
    ExecutionTraceRead,
    EvaluationRunProgress,
    RegressionCheckRequest,
    RunComparisonResult,
    StartEvaluationRequest,
)
from app.services.comparison import compare_runs
from app.services.evaluation import run_evaluation

router = APIRouter(prefix="/runs", tags=["evaluation runs"])


@router.get("/{run_id}/progress", response_model=EvaluationRunProgress)
def get_run_progress(run_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    run = db.get(EvaluationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    counts = db.execute(
        select(EvaluationCase.status, func.count(EvaluationCase.id))
        .where(EvaluationCase.run_id == run_id)
        .group_by(EvaluationCase.status)
    ).all()
    completed = sum(count for case_status, count in counts if case_status.value == "completed")
    failed = sum(count for case_status, count in counts if case_status.value == "failed")
    total = sum(count for _, count in counts)
    return {
        "id": run.id,
        "status": run.status,
        "total_cases": total,
        "completed_cases": completed,
        "failed_cases": failed,
        "pending_cases": max(0, total - completed - failed),
    }


@router.post(
    "",
    response_model=EvaluationRunDetail,
    status_code=status.HTTP_201_CREATED,
)
def start_run(
    payload: StartEvaluationRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> EvaluationRun:
    try:
        run = run_evaluation(
            db,
            dataset_id=payload.dataset_id,
            name=payload.name,
            provider_name=payload.provider or get_settings().llm_provider,
            request_id=request.state.request_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    run.cases.sort(key=lambda case: case.name.casefold())
    return run


@router.post("/compare", response_model=RunComparisonResult)
def compare_run_endpoint(
    payload: CompareRunsRequest,
    db: Session = Depends(get_db),
) -> RunComparisonResult:
    comparison = compare_runs(
        db,
        previous_run_id=payload.previous_run_id,
        current_run_id=payload.current_run_id,
        thresholds=payload.thresholds,
    )
    if comparison is None:
        raise HTTPException(status_code=404, detail="One or both evaluation runs not found")
    return comparison


@router.post("/{run_id}/regressions", response_model=RunComparisonResult)
def regression_findings(
    run_id: uuid.UUID,
    payload: RegressionCheckRequest,
    db: Session = Depends(get_db),
) -> RunComparisonResult:
    comparison = compare_runs(
        db,
        previous_run_id=payload.baseline_run_id,
        current_run_id=run_id,
        thresholds=payload.thresholds,
    )
    if comparison is None:
        raise HTTPException(status_code=404, detail="One or both evaluation runs not found")
    return comparison


@router.get("", response_model=list[EvaluationRunRead])
def list_runs(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[EvaluationRun]:
    return list(
        db.scalars(
            select(EvaluationRun)
            .order_by(EvaluationRun.created_at.desc(), EvaluationRun.id)
            .offset(skip)
            .limit(limit)
        ).all()
    )


@router.get("/{run_id}", response_model=EvaluationRunDetail)
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db)) -> EvaluationRun:
    run = db.scalar(
        select(EvaluationRun)
        .where(EvaluationRun.id == run_id)
        .options(selectinload(EvaluationRun.cases))
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    run.cases.sort(key=lambda case: case.name.casefold())
    return run


@router.get("/{run_id}/cases/{case_id}", response_model=EvaluationCaseRead)
def get_case_result(
    run_id: uuid.UUID,
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> EvaluationCase:
    case = db.scalar(
        select(EvaluationCase).where(
            EvaluationCase.run_id == run_id,
            EvaluationCase.id == case_id,
        )
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Evaluation case result not found")
    return case


@router.get("/{run_id}/traces", response_model=list[ExecutionTraceRead])
def list_run_traces(run_id: uuid.UUID, db: Session = Depends(get_db)) -> list[ExecutionTrace]:
    run = db.get(EvaluationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return list(
        db.scalars(
            select(ExecutionTrace)
            .where(ExecutionTrace.run_id == run_id)
            .order_by(ExecutionTrace.started_at, ExecutionTrace.id)
        ).all()
    )


@router.get("/{run_id}/traces/{trace_id}", response_model=ExecutionTraceRead)
def get_run_trace(
    run_id: uuid.UUID,
    trace_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ExecutionTrace:
    trace = db.scalar(
        select(ExecutionTrace).where(
            ExecutionTrace.run_id == run_id,
            ExecutionTrace.id == trace_id,
        )
    )
    if trace is None:
        raise HTTPException(status_code=404, detail="Execution trace not found")
    return trace
