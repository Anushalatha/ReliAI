import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

json_type = JSON().with_variant(JSONB, "postgresql")


class EvaluationRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvaluationCaseStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExecutionTraceStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class BenchmarkStatus(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


def enum_column(enum_type: type[enum.Enum]) -> Enum:
    return Enum(
        enum_type,
        name=f"{enum_type.__name__.lower()}",
        values_callable=lambda members: [member.value for member in members],
        native_enum=False,
        create_constraint=True,
    )


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("evaluation_datasets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    benchmark_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("benchmarks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[EvaluationRunStatus] = mapped_column(
        enum_column(EvaluationRunStatus),
        nullable=False,
        default=EvaluationRunStatus.PENDING,
    )
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(json_type, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cases: Mapped[list["EvaluationCase"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    traces: Mapped[list["ExecutionTrace"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    dataset: Mapped["EvaluationDataset | None"] = relationship(back_populates="runs")
    benchmark: Mapped["Benchmark | None"] = relationship(back_populates="runs")
    project: Mapped["AIProject | None"] = relationship(back_populates="runs")


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_case_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("dataset_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[EvaluationCaseStatus] = mapped_column(
        enum_column(EvaluationCaseStatus),
        nullable=False,
        default=EvaluationCaseStatus.PENDING,
    )
    input_data: Mapped[dict[str, Any]] = mapped_column(json_type, nullable=False)
    expected_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_json: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reference_keywords: Mapped[list[str] | None] = mapped_column(json_type, nullable=True)
    actual_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(json_type, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[EvaluationRun] = relationship(back_populates="cases")
    traces: Mapped[list["ExecutionTrace"]] = relationship(back_populates="case")
    dataset_case: Mapped["DatasetCase | None"] = relationship(back_populates="results")


class ExecutionTrace(Base):
    __tablename__ = "execution_traces"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("evaluation_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    operation_name: Mapped[str] = mapped_column(String(200), nullable=False, default="evaluation.case")
    status: Mapped[ExecutionTraceStatus] = mapped_column(
        enum_column(ExecutionTraceStatus),
        nullable=False,
        default=ExecutionTraceStatus.RUNNING,
    )
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    trace_metadata: Mapped[dict[str, Any] | None] = mapped_column(json_type, nullable=True)

    run: Mapped[EvaluationRun] = relationship(back_populates="traces")
    case: Mapped[EvaluationCase | None] = relationship(back_populates="traces")


class EvaluationDataset(Base):
    __tablename__ = "evaluation_datasets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    import_status: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    import_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    import_key: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    validation_errors: Mapped[list[dict[str, Any]] | None] = mapped_column(json_type, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    cases: Mapped[list["DatasetCase"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetCase.position",
    )
    runs: Mapped[list[EvaluationRun]] = relationship(back_populates="dataset")
    benchmarks: Mapped[list["Benchmark"]] = relationship(back_populates="dataset")


class Benchmark(Base):
    __tablename__ = "benchmarks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("evaluation_datasets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[BenchmarkStatus] = mapped_column(
        enum_column(BenchmarkStatus), nullable=False, default=BenchmarkStatus.RUNNING
    )
    providers: Mapped[list[str]] = mapped_column(json_type, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    dataset: Mapped[EvaluationDataset | None] = relationship(back_populates="benchmarks")
    runs: Mapped[list[EvaluationRun]] = relationship(back_populates="benchmark")


class DatasetCase(Base):
    __tablename__ = "dataset_cases"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "position",
            name="uq_dataset_cases_dataset_id_position",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("evaluation_datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    input_data: Mapped[dict[str, Any]] = mapped_column(json_type, nullable=False)
    expected_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_json: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reference_keywords: Mapped[list[str] | None] = mapped_column(json_type, nullable=True)
    case_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", json_type, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    dataset: Mapped[EvaluationDataset] = relationship(back_populates="cases")
    results: Mapped[list[EvaluationCase]] = relationship(back_populates="dataset_case")


class AIProject(Base):
    __tablename__ = "ai_projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(Text, nullable=False)
    http_method: Mapped[str] = mapped_column(String(10), nullable=False, default="POST")
    request_template: Mapped[dict[str, Any]] = mapped_column(json_type, nullable=False)
    response_path: Mapped[str] = mapped_column(String(500), nullable=False)
    auth_env_var: Mapped[str | None] = mapped_column(String(200), nullable=True)
    auth_header: Mapped[str] = mapped_column(String(100), nullable=False, default="Authorization")
    auth_scheme: Mapped[str] = mapped_column(String(50), nullable=False, default="Bearer")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    runs: Mapped[list[EvaluationRun]] = relationship(back_populates="project")
