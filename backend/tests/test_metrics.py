from app.services.metrics import aggregate_metrics, evaluate_metrics, unavailable_metrics


def test_metrics_calculate_exact_json_and_keyword_scores():
    metrics = evaluate_metrics(
        '{"answer": "Blue sky"}',
        expected_output='{"answer": "Blue sky"}',
        expected_json=True,
        reference_keywords=["blue", "sky", "ocean"],
    )

    assert metrics["exact_match"] == {"value": 1.0, "available": True}
    assert metrics["structured_output_valid"] == {"value": 1.0, "available": True}
    assert metrics["reference_keyword_coverage"] == {
        "value": 2 / 3,
        "available": True,
    }


def test_invalid_expected_json_scores_zero():
    metrics = evaluate_metrics(
        "not-json",
        expected_output=None,
        expected_json=True,
        reference_keywords=None,
    )

    assert metrics["exact_match"] == {"value": None, "available": False}
    assert metrics["structured_output_valid"] == {"value": 0.0, "available": True}
    assert metrics["reference_keyword_coverage"] == {"value": None, "available": False}


def test_unavailable_metrics_are_not_zero():
    aggregate = aggregate_metrics([unavailable_metrics()])

    assert all(result["value"] is None for result in aggregate.values())
    assert all(result["available_cases"] == 0 for result in aggregate.values())
    assert all(result["total_cases"] == 1 for result in aggregate.values())


def test_keyword_coverage_is_case_insensitive():
    metrics = evaluate_metrics(
        "ReliAI stores traces",
        expected_output=None,
        expected_json=False,
        reference_keywords=["reliai", "runs"],
    )

    assert metrics["reference_keyword_coverage"]["value"] == 0.5
