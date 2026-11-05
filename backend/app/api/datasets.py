import uuid
import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import get_db
from app.models.evaluation import DatasetCase, EvaluationDataset
from app.services.dataset_import import (
    DatasetImportError,
    csv_columns,
    file_digest,
    preview_import,
    validated_import_cases,
)
from app.schemas import (
    DatasetCreate,
    DatasetImportColumns,
    DatasetImportPreview,
    DatasetImportResult,
    DatasetListItem,
    DatasetRead,
    DatasetStoredValidation,
    DatasetValidationResult,
    validate_dataset_payload,
)

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("/validate", response_model=DatasetValidationResult)
def validate_dataset(payload: dict[str, Any]) -> DatasetValidationResult:
    try:
        dataset = validate_dataset_payload(payload)
    except ValidationError as exc:
        return DatasetValidationResult(
            valid=False,
            errors=[
                {"location": error["loc"], "message": error["msg"], "type": error["type"]}
                for error in exc.errors()
            ],
        )
    return DatasetValidationResult(valid=True, case_count=len(dataset.cases))


@router.post(
    "",
    response_model=DatasetRead,
    status_code=status.HTTP_201_CREATED,
)
def create_dataset(payload: DatasetCreate, db: Session = Depends(get_db)) -> EvaluationDataset:
    dataset = EvaluationDataset(name=payload.name, description=payload.description)
    dataset.cases = [
        DatasetCase(
            position=position,
            name=case.name,
            input_data=case.input_data,
            expected_output=case.expected_output,
            expected_json=case.expected_json,
            reference_keywords=case.reference_keywords,
            case_metadata=case.metadata,
        )
        for position, case in enumerate(payload.cases)
    ]
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


def _column_mapping(value: str | None) -> dict[str, str] | None:
    if not value:
        return None
    try:
        mapping = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Column mapping must be valid JSON") from exc
    allowed = {"input_data", "input", "name", "case_id", "expected_output", "reference_keywords", "expected_json", "expect_valid_json"}
    if not isinstance(mapping, dict) or set(mapping) - allowed or any(
        not isinstance(column, str) for column in mapping.values()
    ):
        raise HTTPException(status_code=422, detail="Column mapping contains unsupported fields")
    return mapping


@router.post("/import/columns", response_model=DatasetImportColumns)
async def dataset_import_columns(file: UploadFile = File(...)) -> DatasetImportColumns:
    settings = get_settings()
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > settings.dataset_import_max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.dataset_import_max_bytes}-byte upload limit",
        )
    try:
        columns = csv_columns(file.file, file.filename or "")
    except DatasetImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DatasetImportColumns(
        columns=columns,
        max_bytes=settings.dataset_import_max_bytes,
        max_cases=settings.dataset_import_max_cases,
    )


@router.post("/import/preview", response_model=DatasetImportPreview)
async def preview_dataset_import(
    file: UploadFile = File(...),
    column_mapping: str | None = Form(default=None),
) -> DatasetImportPreview:
    try:
        return preview_import(
            file.file,
            file.filename or "",
            column_mapping=_column_mapping(column_mapping),
        )
    except DatasetImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/import", response_model=DatasetImportResult, status_code=status.HTTP_201_CREATED)
async def import_dataset(
    file: UploadFile = File(...),
    name: str = Form(..., min_length=1, max_length=200),
    description: str | None = Form(default=None, max_length=4000),
    invalid_policy: str = Form(default="reject"),
    column_mapping: str | None = Form(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=100),
    db: Session = Depends(get_db),
) -> DatasetImportResult:
    if invalid_policy not in {"reject", "valid_only"}:
        raise HTTPException(status_code=422, detail="invalid_policy must be reject or valid_only")
    if idempotency_key is not None and not idempotency_key.strip():
        raise HTTPException(status_code=422, detail="Idempotency-Key must not be empty")
    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip()
    mapping = _column_mapping(column_mapping)
    file_name = file.filename or ""
    try:
        preview = preview_import(file.file, file_name, column_mapping=mapping)
        digest = file_digest(file.file, mapping)
    except DatasetImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if preview.total_rows == 0:
        raise HTTPException(status_code=422, detail="Import file contains no cases")
    if preview.valid_cases == 0:
        raise HTTPException(
            status_code=422,
            detail={"message": "Import has no valid cases", "report": preview.model_dump(mode="json")},
        )
    if invalid_policy == "reject" and preview.invalid_cases:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Import rejected because invalid rows were found",
                "report": preview.model_dump(mode="json"),
            },
        )

    existing = None
    if idempotency_key:
        existing = db.scalar(
            select(EvaluationDataset)
            .where(EvaluationDataset.import_key == idempotency_key)
            .options(selectinload(EvaluationDataset.cases))
        )
    if existing is not None:
        if existing.import_sha256 != digest:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key was already used for a different import",
            )
        return DatasetImportResult(
            dataset=DatasetRead.model_validate(existing),
            created_cases=0,
            rejected_cases=preview.invalid_cases,
            duplicate_submission=True,
        )
    existing = db.scalar(
        select(EvaluationDataset)
        .where(EvaluationDataset.import_sha256 == digest)
        .options(selectinload(EvaluationDataset.cases))
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"This file was already imported as dataset '{existing.name}'",
        )

    dataset = EvaluationDataset(
        name=name.strip(),
        description=description.strip() if description and description.strip() else None,
        source_file_name=file_name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:255],
        import_status="partial" if preview.invalid_cases else "completed",
        import_sha256=digest,
        import_key=idempotency_key,
        validation_errors=[issue.model_dump() for issue in preview.errors] or None,
    )
    try:
        db.add(dataset)
        db.flush()
        batch_size = get_settings().dataset_import_batch_size
        batch: list[dict[str, Any]] = []
        position = 0
        await file.seek(0)
        for _, case in validated_import_cases(file.file, file_name, column_mapping=mapping):
            batch.append(
                {
                    "dataset_id": dataset.id,
                    "name": case.name,
                    "position": position,
                    "input_data": case.input_data,
                    "expected_output": case.expected_output,
                    "expected_json": case.expected_json,
                    "reference_keywords": case.reference_keywords,
                    "case_metadata": case.metadata,
                }
            )
            position += 1
            if len(batch) >= batch_size:
                db.execute(insert(DatasetCase), batch)
                batch.clear()
        if batch:
            db.execute(insert(DatasetCase), batch)
        db.commit()
    except (DatasetImportError, IntegrityError) as exc:
        db.rollback()
        if isinstance(exc, IntegrityError):
            raise HTTPException(status_code=409, detail="This import was already submitted") from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    stored = db.scalar(
        select(EvaluationDataset)
        .where(EvaluationDataset.id == dataset.id)
        .options(selectinload(EvaluationDataset.cases))
    )
    if stored is None:
        raise HTTPException(status_code=500, detail="Imported dataset could not be loaded")
    return DatasetImportResult(
        dataset=DatasetRead.model_validate(stored),
        created_cases=position,
        rejected_cases=preview.invalid_cases,
    )


@router.post("/{dataset_id}/validate", response_model=DatasetStoredValidation)
def validate_stored_dataset(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DatasetStoredValidation:
    dataset = db.scalar(
        select(EvaluationDataset)
        .where(EvaluationDataset.id == dataset_id)
        .options(selectinload(EvaluationDataset.cases))
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    names: set[str] = set()
    issues = []
    for position, case in enumerate(dataset.cases, start=1):
        identifier = case.name.casefold()
        if identifier in names:
            issues.append({"row": position, "case_id": case.name, "message": "duplicate identifier"})
        names.add(identifier)
        if not isinstance(case.input_data, dict):
            issues.append({"row": position, "case_id": case.name, "message": "input_data must be an object"})
    return DatasetStoredValidation(
        dataset_id=dataset.id,
        valid_cases=len(dataset.cases) - len(issues),
        invalid_cases=len(issues),
        duplicate_identifiers=sum(issue["message"] == "duplicate identifier" for issue in issues),
        errors=issues,
    )


@router.get("", response_model=list[DatasetListItem])
def list_datasets(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[DatasetListItem]:
    datasets = db.execute(
        select(
            EvaluationDataset.id,
            EvaluationDataset.name,
            EvaluationDataset.description,
            EvaluationDataset.created_at,
            EvaluationDataset.source_file_name,
            EvaluationDataset.import_status,
            func.count(DatasetCase.id).label("case_count"),
        )
        .outerjoin(DatasetCase)
        .group_by(EvaluationDataset.id)
        .order_by(EvaluationDataset.created_at.desc(), EvaluationDataset.id)
        .offset(skip)
        .limit(limit)
    ).all()
    return [
        DatasetListItem(
            id=row.id,
            name=row.name,
            description=row.description,
            created_at=row.created_at,
            source_file_name=row.source_file_name,
            import_status=row.import_status,
            case_count=row.case_count,
        )
        for row in datasets
    ]


@router.get("/{dataset_id}", response_model=DatasetRead)
def get_dataset(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> EvaluationDataset:
    dataset = db.scalar(
        select(EvaluationDataset)
        .where(EvaluationDataset.id == dataset_id)
        .options(selectinload(EvaluationDataset.cases))
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset
