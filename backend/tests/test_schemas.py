from datetime import datetime, timezone
import uuid

import pytest
from pydantic import ValidationError

from app.models.evaluation import EvaluationCaseStatus, EvaluationRunStatus, ExecutionTraceStatus
from app.schemas import EvaluationCaseRead, EvaluationRunRead, ExecutionTraceRead


def test_run_schema_validates_persisted_shape():
    value = EvaluationRunRead(
        id=uuid.uuid4(),
        name="smoke test",
        status=EvaluationRunStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )

    assert value.status == EvaluationRunStatus.PENDING
    assert value.model_name is None


def test_case_schema_rejects_score_outside_unit_interval():
    with pytest.raises(ValidationError):
        EvaluationCaseRead(
            id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            name="case",
            status=EvaluationCaseStatus.COMPLETED,
            input_data={},
            score=1.5,
            created_at=datetime.now(timezone.utc),
        )


def test_trace_schema_allows_unavailable_optional_data():
    trace = ExecutionTraceRead(
        id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        status=ExecutionTraceStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )

    assert trace.input_tokens is None
    assert trace.model_name is None


def test_trace_schema_rejects_negative_latency():
    with pytest.raises(ValidationError):
        ExecutionTraceRead(
            id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            status=ExecutionTraceStatus.FAILED,
            started_at=datetime.now(timezone.utc),
            latency_ms=-1,
        )
