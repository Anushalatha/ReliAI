import json
from typing import Any


METRIC_NAMES = (
    "exact_match",
    "structured_output_valid",
    "reference_keyword_coverage",
)


def evaluate_metrics(
    output: str,
    *,
    expected_output: str | None,
    expected_json: bool,
    reference_keywords: list[str] | None,
) -> dict[str, dict[str, float | bool | None]]:
    exact_match: float | None = None
    if expected_output is not None:
        exact_match = float(output == expected_output)

    structured_valid: float | None = None
    if expected_json:
        try:
            json.loads(output)
            structured_valid = 1.0
        except json.JSONDecodeError:
            structured_valid = 0.0

    keyword_coverage: float | None = None
    if reference_keywords is not None:
        output_folded = output.casefold()
        keyword_coverage = sum(
            keyword.casefold() in output_folded for keyword in reference_keywords
        ) / len(reference_keywords)

    values = (exact_match, structured_valid, keyword_coverage)
    return {
        name: {"value": value, "available": value is not None}
        for name, value in zip(METRIC_NAMES, values, strict=True)
    }


def unavailable_metrics() -> dict[str, dict[str, float | bool | None]]:
    return {
        name: {"value": None, "available": False}
        for name in METRIC_NAMES
    }


def aggregate_metrics(
    case_metrics: list[dict[str, dict[str, Any]]],
) -> dict[str, dict[str, float | int | None]]:
    totals: dict[str, dict[str, float | int | None]] = {}
    for metric_name in METRIC_NAMES:
        values = [
            metric[metric_name]["value"]
            for metric in case_metrics
            if metric[metric_name]["available"]
        ]
        totals[metric_name] = {
            "value": sum(values) / len(values) if values else None,
            "available_cases": len(values),
            "total_cases": len(case_metrics),
        }
    return totals
