import csv
import hashlib
import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, BinaryIO

import ijson
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas import DatasetCaseCreate, DatasetImportIssue, DatasetImportPreview

SAMPLE_CASE_LIMIT = 5


class DatasetImportError(ValueError):
    pass


def file_digest(source: BinaryIO, column_mapping: dict[str, str] | None = None) -> str:
    digest = hashlib.sha256()
    source.seek(0)
    while chunk := source.read(64 * 1024):
        digest.update(chunk)
    if column_mapping:
        digest.update(
            json.dumps(column_mapping, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
    source.seek(0)
    return digest.hexdigest()


def _format_from_name(file_name: str) -> str:
    suffix = Path(file_name).suffix.casefold()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    if suffix in (".jsonl", ".ndjson"):
        return "jsonl"
    raise DatasetImportError("Supported file formats are CSV, JSON, JSONL, and NDJSON")


def _csv_rows(source: BinaryIO, column_mapping: dict[str, str]) -> Iterator[tuple[int, Any]]:
    text = io.TextIOWrapper(source, encoding="utf-8-sig", newline="")
    try:
        reader = csv.DictReader(text, strict=True)
        if not reader.fieldnames:
            raise DatasetImportError("CSV file must include a header row")
        if any(not field.strip() for field in reader.fieldnames):
            raise DatasetImportError("CSV headers must not be empty")
        if len({field.casefold() for field in reader.fieldnames}) != len(reader.fieldnames):
            raise DatasetImportError("CSV headers must be unique")
        for line_number, row in enumerate(reader, start=2):
            yield line_number, {key: row.get(column) for key, column in column_mapping.items() if column}
    except (UnicodeDecodeError, csv.Error) as exc:
        raise DatasetImportError("CSV file must use valid UTF-8 CSV data") from exc
    finally:
        text.detach()
        source.seek(0)


def _json_rows(source: BinaryIO) -> Iterator[tuple[int, Any]]:
    source.seek(0)
    first = source.read(1)
    while first in (b" ", b"\t", b"\r", b"\n"):
        first = source.read(1)
    source.seek(0)
    try:
        if first == b"[":
            rows = ijson.items(source, "item", use_float=True)
        elif first == b"{":
            events = iter(ijson.parse(source))
            next(events)
            has_cases_array = False
            for prefix, event, value in events:
                if prefix == "" and event == "map_key" and value == "cases":
                    next_prefix, next_event, _ = next(events)
                    if next_prefix != "cases" or next_event != "start_array":
                        raise DatasetImportError("JSON object must contain a cases array")
                    has_cases_array = True
                    break
            if not has_cases_array:
                raise DatasetImportError("JSON object must contain a cases array")
            source.seek(0)
            rows = ijson.items(source, "cases.item", use_float=True)
        else:
            raise DatasetImportError("JSON file must contain an array or an object with a cases array")
        for row_number, row in enumerate(rows, start=1):
            yield row_number, row
    except (ijson.common.JSONError, UnicodeDecodeError, OverflowError) as exc:
        raise DatasetImportError("Malformed JSON file") from exc
    finally:
        source.seek(0)


def _jsonl_rows(source: BinaryIO) -> Iterator[tuple[int, Any]]:
    source.seek(0)
    for row_number, line in enumerate(source, start=1):
        if not line.strip():
            continue
        try:
            yield row_number, json.loads(
                line,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(f"Invalid JSON constant: {value}")
                ),
            )
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            yield row_number, None
    source.seek(0)


def _rows(
    source: BinaryIO,
    file_name: str,
    column_mapping: dict[str, str] | None,
) -> Iterator[tuple[int, Any]]:
    file_format = _format_from_name(file_name)
    if file_format == "csv":
        yield from _csv_rows(source, column_mapping or {})
    elif file_format == "json":
        yield from _json_rows(source)
    else:
        yield from _jsonl_rows(source)


def csv_columns(source: BinaryIO, file_name: str) -> list[str]:
    if _format_from_name(file_name) != "csv":
        return []
    source.seek(0)
    try:
        text = io.TextIOWrapper(source, encoding="utf-8-sig", newline="")
        reader = csv.reader(text)
        columns = next(reader, [])
        return [column.strip() for column in columns]
    except (UnicodeDecodeError, csv.Error) as exc:
        raise DatasetImportError("Unable to read CSV headers") from exc
    finally:
        if "text" in locals():
            text.detach()
        source.seek(0)


def _normalize_case(
    row: Any,
    file_format: str,
    column_mapping: dict[str, str] | None,
    default_name: str,
) -> tuple[DatasetCaseCreate, str]:
    if not isinstance(row, dict):
        raise ValueError("case must be a JSON object")
    if file_format == "csv":
        raw = row
    else:
        raw = row

    identifier = raw.get("case_id") or raw.get("name")
    if identifier is not None and not isinstance(identifier, (str, int)):
        raise ValueError("name or case_id must be a string or integer")
    name = str(identifier).strip() if identifier is not None else default_name
    if not name:
        name = default_name

    if "input_data" not in raw or raw["input_data"] is None:
        raise ValueError("input_data is required")
    input_data = raw["input_data"]
    if file_format == "csv" and isinstance(input_data, str):
        try:
            input_data = json.loads(input_data)
        except json.JSONDecodeError:
            input_data = {"prompt": input_data}
    if isinstance(input_data, dict):
        normalized_input = input_data
    elif isinstance(input_data, str):
        normalized_input = {"prompt": input_data}
    else:
        normalized_input = {"value": input_data}

    expected_output = raw.get("expected_output")
    if expected_output is not None:
        if file_format == "csv" and isinstance(expected_output, str):
            expected_output = expected_output if expected_output.strip() else None
        elif not isinstance(expected_output, str):
            expected_output = json.dumps(
                expected_output, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )

    keywords = raw.get("reference_keywords")
    if isinstance(keywords, str):
        keywords = [word.strip() for word in keywords.split(",") if word.strip()]
    elif keywords is not None and not isinstance(keywords, list):
        raise ValueError("reference_keywords must be a list of strings or comma-separated text")
    if keywords == []:
        keywords = None

    expected_json = raw.get("expect_valid_json", raw.get("expected_json", False))
    if file_format == "csv" and isinstance(expected_json, str):
        expected_json = expected_json.strip().casefold() in {"true", "1", "yes", "y"}

    metadata = raw.get("metadata")
    case = DatasetCaseCreate.model_validate(
        {
            "name": name,
            "input_data": normalized_input,
            "expected_output": expected_output,
            "expected_json": expected_json,
            "reference_keywords": keywords,
            "metadata": metadata,
        }
    )
    return case, name


def preview_import(
    source: BinaryIO,
    file_name: str,
    *,
    column_mapping: dict[str, str] | None = None,
) -> DatasetImportPreview:
    file_format = _format_from_name(file_name)
    source.seek(0, io.SEEK_END)
    size = source.tell()
    source.seek(0)
    if size > get_settings().dataset_import_max_bytes:
        raise DatasetImportError(
            f"File exceeds the {get_settings().dataset_import_max_bytes}-byte upload limit"
        )

    columns = csv_columns(source, file_name)
    if file_format == "csv":
        mapping = column_mapping or {}
        input_column = mapping.get("input_data") or mapping.get("input")
        if input_column not in columns:
            raise DatasetImportError("CSV mapping must select an input_data column")
        resolved_mapping = {
            "input_data": input_column,
            "name": mapping.get("name") or mapping.get("case_id") or "",
            "expected_output": mapping.get("expected_output", ""),
            "reference_keywords": mapping.get("reference_keywords", ""),
            "expected_json": mapping.get("expect_valid_json") or mapping.get("expected_json") or "",
        }
    else:
        resolved_mapping = None

    max_cases = get_settings().dataset_import_max_cases
    seen: set[str] = set()
    errors: list[DatasetImportIssue] = []
    sample_cases: list[DatasetCaseCreate] = []
    total_rows = valid_cases = invalid_cases = missing_expected = duplicates = 0
    for row_number, row in _rows(source, file_name, resolved_mapping):
        total_rows += 1
        if total_rows > max_cases:
            invalid_cases += 1
            errors.append(
                DatasetImportIssue(row=row_number, message=f"Case count exceeds the {max_cases}-case limit")
            )
            continue
        try:
            case, identifier = _normalize_case(
                row, file_format, resolved_mapping, f"case_{row_number:06d}"
            )
            folded = identifier.casefold()
            if folded in seen:
                duplicates += 1
                raise ValueError(f"duplicate identifier: {identifier}")
            seen.add(folded)
            if case.expected_output is None:
                missing_expected += 1
            valid_cases += 1
            if len(sample_cases) < SAMPLE_CASE_LIMIT:
                sample_cases.append(case)
        except (ValueError, ValidationError, TypeError) as exc:
            invalid_cases += 1
            identifier = row.get("case_id") or row.get("name") if isinstance(row, dict) else None
            errors.append(
                DatasetImportIssue(
                    row=row_number,
                    case_id=str(identifier) if identifier is not None else None,
                    message=str(exc)[:500],
                )
            )

    return DatasetImportPreview(
        file_name=Path(file_name).name[:255],
        format=file_format,
        total_rows=total_rows,
        valid_cases=valid_cases,
        invalid_cases=invalid_cases,
        missing_expected_outputs=missing_expected,
        duplicate_identifiers=duplicates,
        columns=columns,
        max_bytes=get_settings().dataset_import_max_bytes,
        max_cases=max_cases,
        errors=errors,
        sample_cases=sample_cases,
    )


def validated_import_cases(
    source: BinaryIO,
    file_name: str,
    *,
    column_mapping: dict[str, str] | None = None,
) -> Iterator[tuple[int, DatasetCaseCreate]]:
    file_format = _format_from_name(file_name)
    if file_format == "csv":
        mapping = column_mapping or {}
        resolved_mapping = {
            "input_data": mapping.get("input_data") or mapping.get("input") or "",
            "name": mapping.get("name") or mapping.get("case_id") or "",
            "expected_output": mapping.get("expected_output", ""),
            "reference_keywords": mapping.get("reference_keywords", ""),
            "expected_json": mapping.get("expect_valid_json") or mapping.get("expected_json") or "",
        }
    else:
        resolved_mapping = None
    seen: set[str] = set()
    max_cases = get_settings().dataset_import_max_cases
    row_count = 0
    for row_number, row in _rows(source, file_name, resolved_mapping):
        row_count += 1
        if row_count > max_cases:
            break
        try:
            case, _ = _normalize_case(
                row, file_format, resolved_mapping, f"case_{row_number:06d}"
            )
            folded_name = case.name.casefold()
            if folded_name in seen:
                continue
            seen.add(folded_name)
            yield row_number, case
        except (ValueError, ValidationError, TypeError):
            continue
