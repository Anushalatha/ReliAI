import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from app.models.evaluation import (
    AIProject,
    BenchmarkStatus,
    EvaluationCaseStatus,
    EvaluationRunStatus,
    ExecutionTraceStatus,
)

DatasetName = Annotated[
    str, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)
]


class EvaluationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID | None = None
    benchmark_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    name: str
    status: EvaluationRunStatus
    provider: str | None = None
    model_name: str | None = None
    metrics: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class BenchmarkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: uuid.UUID
    name: DatasetName | None = None
    providers: list[Literal["mock", "groq"]] = Field(min_length=1, max_length=2)
    groq_model: Annotated[
        str | None, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)
    ] = None

    @model_validator(mode="after")
    def validate_providers(self):
        if len(set(self.providers)) != len(self.providers):
            raise ValueError("providers must be unique")
        return self


class BenchmarkListItem(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID | None
    name: str
    status: BenchmarkStatus
    providers: list[str]
    created_at: datetime
    completed_at: datetime | None


class BenchmarkMetricSummary(BaseModel):
    value: float | None
    sample_count: int


class BenchmarkLatencySummary(BaseModel):
    average_ms: float | None
    median_ms: float | None
    p50_ms: float | None
    p95_ms: float | None
    sample_count: int
    p95_minimum_samples: int


class BenchmarkTokenSummary(BaseModel):
    average_tokens: float | None
    total_tokens: int | None
    sample_count: int


class BenchmarkCaseOutcomeSummary(BaseModel):
    attempts: int
    successes: int
    failures: int
    success_rate: float | None
    failure_rate: float | None
    sample_count: int


class BenchmarkRunOutcomeSummary(BaseModel):
    completed: int
    failed: int
    sample_count: int


class BenchmarkProviderResult(BaseModel):
    provider: str
    models: list[str]
    run_ids: list[uuid.UUID]
    run_outcomes: BenchmarkRunOutcomeSummary
    quality_metrics: dict[str, BenchmarkMetricSummary]
    latency: BenchmarkLatencySummary
    input_tokens: BenchmarkTokenSummary
    output_tokens: BenchmarkTokenSummary
    case_outcomes: BenchmarkCaseOutcomeSummary
    error_counts: dict[str, int]


class BenchmarkDetail(BenchmarkListItem):
    dataset_name: str | None
    case_count: int
    results: list[BenchmarkProviderResult]


class BenchmarkSummaryRead(BaseModel):
    provider_results: list[BenchmarkProviderResult]
    recent_benchmarks: list[BenchmarkListItem]


class EvaluationCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    name: str
    dataset_case_id: uuid.UUID | None = None
    status: EvaluationCaseStatus
    input_data: dict[str, Any]
    expected_output: str | None = None
    expected_json: bool
    reference_keywords: list[str] | None = None
    actual_output: str | None = None
    score: float | None = Field(default=None, ge=0, le=1)
    metrics: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ExecutionTraceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    case_id: uuid.UUID | None = None
    request_id: str | None = None
    operation_name: str = "evaluation.case"
    status: ExecutionTraceStatus
    provider: str | None = None
    model_name: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    error_type: str | None = None
    error_message: str | None = None
    error_details: dict[str, Any] | None = None
    trace_metadata: dict[str, Any] | None = None


class DatasetCaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: DatasetName
    input_data: dict[str, Any]
    expected_output: str | None = None
    expected_json: bool = False
    reference_keywords: list[str] | None = Field(default=None, min_length=1)
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_keywords(self):
        if self.reference_keywords is not None:
            cleaned = [keyword.strip() for keyword in self.reference_keywords]
            if any(not keyword for keyword in cleaned):
                raise ValueError("reference keywords must not be empty")
            self.reference_keywords = cleaned
        return self


class DatasetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: DatasetName
    description: str | None = None
    cases: list[DatasetCaseCreate] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_unique_case_names(self):
        names = [case.name.casefold() for case in self.cases]
        if len(names) != len(set(names)):
            raise ValueError("case names must be unique within a dataset")
        return self


class DatasetCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    name: str
    position: int
    input_data: dict[str, Any]
    expected_output: str | None = None
    expected_json: bool
    reference_keywords: list[str] | None = None
    metadata: dict[str, Any] | None = Field(default=None, validation_alias="case_metadata")
    created_at: datetime


class DatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    source_file_name: str | None = None
    import_status: str = "manual"
    validation_errors: list[dict[str, Any]] | None = None
    created_at: datetime
    cases: list[DatasetCaseRead]


class DatasetListItem(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    created_at: datetime
    case_count: int
    source_file_name: str | None = None
    import_status: str = "manual"


class DatasetValidationResult(BaseModel):
    valid: bool
    case_count: int | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)


class DatasetImportIssue(BaseModel):
    row: int
    case_id: str | None = None
    message: str


class DatasetImportPreview(BaseModel):
    file_name: str
    format: Literal["csv", "json", "jsonl"]
    total_rows: int
    valid_cases: int
    invalid_cases: int
    missing_expected_outputs: int
    duplicate_identifiers: int
    columns: list[str] = Field(default_factory=list)
    max_bytes: int
    max_cases: int
    errors: list[DatasetImportIssue]
    sample_cases: list[DatasetCaseCreate] = Field(default_factory=list)


class DatasetImportColumns(BaseModel):
    columns: list[str]
    max_bytes: int
    max_cases: int


class DatasetImportResult(BaseModel):
    dataset: DatasetRead
    created_cases: int
    rejected_cases: int
    duplicate_submission: bool = False


class DatasetStoredValidation(BaseModel):
    dataset_id: uuid.UUID
    valid_cases: int
    invalid_cases: int
    duplicate_identifiers: int
    errors: list[DatasetImportIssue]


class AIProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: DatasetName
    endpoint_url: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    http_method: Literal["POST", "PUT"] = "POST"
    request_template: dict[str, Any] = Field(
        default_factory=lambda: {"input": "{{input_data}}"}
    )
    response_path: Annotated[str, StringConstraints(min_length=1, max_length=500)] = "output"
    auth_env_var: Annotated[
        str | None, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{0,199}$")
    ] = None
    auth_header: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9-]{1,100}$")] = "Authorization"
    auth_scheme: Annotated[
        str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9._~-]{0,49}$")
    ] = "Bearer"


class AIProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    endpoint_url: str
    http_method: str
    request_template: dict[str, Any]
    response_path: str
    auth_env_var: str | None
    auth_header: str
    auth_scheme: str
    created_at: datetime


class ProjectEvaluationCreate(BaseModel):
    dataset_id: uuid.UUID
    project_id: uuid.UUID
    name: DatasetName | None = None


class ProjectEvaluationAccepted(BaseModel):
    run_id: uuid.UUID
    status: EvaluationRunStatus


class EvaluationRunProgress(BaseModel):
    id: uuid.UUID
    status: EvaluationRunStatus
    total_cases: int
    completed_cases: int
    failed_cases: int
    pending_cases: int


class EvaluationRunDetail(EvaluationRunRead):
    cases: list[EvaluationCaseRead]


class StartEvaluationRequest(BaseModel):
    dataset_id: uuid.UUID
    name: DatasetName | None = None
    provider: Annotated[
        str | None,
        StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,49}$"),
    ] = None


class CompareRunsRequest(BaseModel):
    previous_run_id: uuid.UUID
    current_run_id: uuid.UUID
    thresholds: dict[str, float] = Field(
        default_factory=lambda: {
            "exact_match": 0.05,
            "structured_output_valid": 0.05,
            "reference_keyword_coverage": 0.05,
            "latency_ms": 100.0,
        }
    )

    @model_validator(mode="after")
    def validate_thresholds(self):
        validate_regression_thresholds(self.thresholds)
        return self


class RegressionCheckRequest(BaseModel):
    baseline_run_id: uuid.UUID
    thresholds: dict[str, float] = Field(
        default_factory=lambda: {
            "exact_match": 0.05,
            "structured_output_valid": 0.05,
            "reference_keyword_coverage": 0.05,
            "latency_ms": 100.0,
        }
    )

    @model_validator(mode="after")
    def validate_thresholds(self):
        validate_regression_thresholds(self.thresholds)
        return self


def validate_regression_thresholds(thresholds: dict[str, float]) -> None:
    supported = {
        "exact_match",
        "structured_output_valid",
        "reference_keyword_coverage",
        "latency_ms",
    }
    unknown = set(thresholds) - supported
    if unknown:
        raise ValueError(f"unsupported regression metrics: {', '.join(sorted(unknown))}")
    if any(value < 0 for value in thresholds.values()):
        raise ValueError("regression thresholds must be non-negative")
    if any(
        metric != "latency_ms" and value > 1
        for metric, value in thresholds.items()
    ):
        raise ValueError("quality metric regression thresholds must not exceed 1")


class MetricComparison(BaseModel):
    metric: str
    direction: Literal["higher_is_better", "lower_is_better"]
    previous_value: float | None = None
    current_value: float | None = None
    difference: float | None = None
    absolute_difference: float | None = None
    available: bool


class CaseComparison(BaseModel):
    dataset_case_id: uuid.UUID
    name: str
    previous_status: EvaluationCaseStatus
    current_status: EvaluationCaseStatus
    previous_score: float | None = None
    current_score: float | None = None
    score_difference: float | None = None
    output_changed: bool | None = None
    newly_failed: bool
    recovered: bool


class RegressionFinding(BaseModel):
    metric: str
    previous_value: float
    current_value: float
    difference: float
    threshold: float
    direction: Literal["higher_is_better", "lower_is_better"]


class RunComparisonResult(BaseModel):
    status: Literal["compatible", "incompatible"]
    previous_run_id: uuid.UUID
    current_run_id: uuid.UUID
    reasons: list[str] = Field(default_factory=list)
    metrics: list[MetricComparison] = Field(default_factory=list)
    cases: list[CaseComparison] = Field(default_factory=list)
    regressions: list[RegressionFinding] = Field(default_factory=list)


def validate_dataset_payload(payload: dict[str, Any]) -> DatasetCreate:
    return TypeAdapter(DatasetCreate).validate_python(payload)
