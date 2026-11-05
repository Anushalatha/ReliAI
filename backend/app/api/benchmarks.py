import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.evaluation import Benchmark
from app.schemas import (
    BenchmarkCreate,
    BenchmarkDetail,
    BenchmarkListItem,
    BenchmarkSummaryRead,
)
from app.services.benchmarking import benchmark_detail, benchmark_summary, run_benchmark

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


@router.post(
    "",
    response_model=BenchmarkDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_benchmark(
    payload: BenchmarkCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    benchmark = run_benchmark(
        db,
        dataset_id=payload.dataset_id,
        name=payload.name,
        providers=payload.providers,
        groq_model=payload.groq_model,
        request_id=request.state.request_id,
    )
    if benchmark is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    result = benchmark_detail(db, benchmark.id)
    if result is None:
        raise HTTPException(status_code=500, detail="Benchmark result could not be loaded")
    return result


@router.get("", response_model=list[BenchmarkListItem])
def list_benchmarks(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[Benchmark]:
    return list(
        db.scalars(
            select(Benchmark)
            .order_by(Benchmark.created_at.desc(), Benchmark.id)
            .offset(skip)
            .limit(limit)
        ).all()
    )


@router.get("/summary", response_model=BenchmarkSummaryRead)
def get_benchmark_summary(
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    return benchmark_summary(db, limit=limit)


@router.get("/{benchmark_id}", response_model=BenchmarkDetail)
def get_benchmark(benchmark_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    result = benchmark_detail(db, benchmark_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    return result
