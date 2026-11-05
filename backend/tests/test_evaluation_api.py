def create_dataset(client, cases=None):
    payload = {
        "name": "mock smoke dataset",
        "description": "Small deterministic fixture",
        "cases": cases
        or [
            {
                "name": "echo answer",
                "input_data": {"prompt": "answer"},
                "expected_output": "answer",
                "reference_keywords": ["answer", "missing"],
            },
            {
                "name": "json response",
                "input_data": {"prompt": {"ok": True}},
                "expected_output": '{"response": {"ok": true}}',
                "expected_json": True,
            },
        ],
    }
    return client.post("/datasets", json=payload)


def test_dataset_create_list_get_and_validate(client):
    payload = {
        "name": "my dataset",
        "cases": [{"name": "first", "input_data": {"prompt": "hello"}}],
    }

    validation = client.post("/datasets/validate", json=payload)
    created = client.post("/datasets", json=payload)
    listed = client.get("/datasets")
    retrieved = client.get(f"/datasets/{created.json()['id']}")

    assert validation.status_code == 200
    assert validation.json() == {"valid": True, "case_count": 1, "errors": []}
    assert created.status_code == 201
    assert listed.status_code == 200
    assert listed.json()[0]["case_count"] == 1
    assert retrieved.json()["cases"][0]["input_data"] == {"prompt": "hello"}


def test_dataset_validation_reports_invalid_structure(client):
    response = client.post(
        "/datasets/validate",
        json={"name": "bad", "cases": [{"name": "duplicate", "input_data": {}} ,
                                        {"name": "DUPLICATE", "input_data": {}}]},
    )

    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert response.json()["errors"]


def test_dataset_create_rejects_empty_cases_and_invalid_json_expectation(client):
    empty = client.post("/datasets", json={"name": "empty", "cases": []})
    invalid_case = client.post(
        "/datasets",
        json={
            "name": "invalid",
            "cases": [
                {
                    "name": "bad",
                    "input_data": {},
                    "reference_keywords": [""],
                }
            ],
        },
    )

    assert empty.status_code == 422
    assert invalid_case.status_code == 422
    assert empty.json()["error"]["message"] == "Request validation failed"


def test_run_persists_metrics_and_case_results_for_retrieval(client):
    dataset = create_dataset(client)
    run_response = client.post(
        "/runs",
        json={"dataset_id": dataset.json()["id"], "provider": "mock"},
    )

    assert run_response.status_code == 201
    run = run_response.json()
    assert run["status"] == "completed"
    assert run["provider"] == "mock"
    assert run["metrics"]["exact_match"]["value"] == 1.0
    assert run["metrics"]["exact_match"]["available_cases"] == 2
    assert run["metrics"]["structured_output_valid"]["value"] == 1.0
    assert run["metrics"]["reference_keyword_coverage"]["value"] == 0.5
    assert all(case["status"] == "completed" for case in run["cases"])

    stored = client.get(f"/runs/{run['id']}")
    result = client.get(f"/runs/{run['id']}/cases/{run['cases'][0]['id']}")
    runs = client.get("/runs")

    assert stored.status_code == 200
    assert len(stored.json()["cases"]) == 2
    assert result.status_code == 200
    assert result.json()["actual_output"] is not None
    assert runs.json()[0]["id"] == run["id"]


def test_failed_case_is_saved_and_metrics_remain_unavailable(client):
    dataset = create_dataset(
        client,
        cases=[
            {
                "name": "broken",
                "input_data": {"mock_error": "mock execution failed"},
                "expected_output": "some answer",
                "expected_json": True,
                "reference_keywords": ["answer"],
            }
        ],
    )

    run = client.post("/runs", json={"dataset_id": dataset.json()["id"]}).json()

    assert run["status"] == "failed"
    assert run["cases"][0]["status"] == "failed"
    assert run["cases"][0]["error_message"] == "mock execution failed"
    assert run["cases"][0]["actual_output"] is None
    assert all(metric["value"] is None for metric in run["metrics"].values())
    assert all(metric["available_cases"] == 0 for metric in run["metrics"].values())


def test_aggregate_metrics_exclude_failed_cases(client):
    dataset = create_dataset(
        client,
        cases=[
            {
                "name": "success",
                "input_data": {"prompt": "known"},
                "expected_output": "known",
            },
            {
                "name": "failure",
                "input_data": {"mock_error": "intentional"},
                "expected_output": "known",
            },
        ],
    )

    run = client.post("/runs", json={"dataset_id": dataset.json()["id"]}).json()

    assert run["status"] == "failed"
    assert run["metrics"]["exact_match"] == {
        "value": 1.0,
        "available_cases": 1,
        "total_cases": 2,
    }


def test_run_api_validates_provider_and_unknown_dataset(client):
    invalid_provider = client.post(
        "/runs",
        json={"dataset_id": "00000000-0000-0000-0000-000000000001", "provider": "gemini"},
    )
    unknown_dataset = client.post(
        "/runs",
        json={"dataset_id": "00000000-0000-0000-0000-000000000001"},
    )

    assert invalid_provider.status_code == 422
    assert unknown_dataset.status_code == 404


def test_run_api_accepts_together_provider_without_credentials_fallback(client, monkeypatch):
    from app.providers.together import TogetherProvider

    monkeypatch.setattr(
        "app.services.evaluation.get_provider",
        lambda name: TogetherProvider(api_key=None, model_name="Qwen/Qwen3.5-9B"),
    )
    dataset = create_dataset(client, cases=[
        {"name": "provider failure", "input_data": {"prompt": "hello"}}
    ])

    response = client.post(
        "/runs",
        json={"dataset_id": dataset.json()["id"], "provider": "together"},
    )

    assert response.status_code == 201
    run = response.json()
    assert run["provider"] == "together"
    assert run["status"] == "failed"
    assert run["cases"][0]["status"] == "failed"
    assert "TOGETHER_API_KEY" in run["cases"][0]["error_message"]


def test_run_api_uses_configured_default_provider(client, monkeypatch):
    from types import SimpleNamespace

    from app.providers.together import TogetherProvider

    monkeypatch.setattr(
        "app.api.runs.get_settings",
        lambda: SimpleNamespace(llm_provider="together"),
    )
    monkeypatch.setattr(
        "app.services.evaluation.get_provider",
        lambda name: TogetherProvider(api_key=None, model_name="configured-model"),
    )
    dataset = create_dataset(client, cases=[
        {"name": "configured provider", "input_data": {"prompt": "hello"}}
    ])

    response = client.post("/runs", json={"dataset_id": dataset.json()["id"]})

    assert response.status_code == 201
    run = response.json()
    assert run["provider"] == "together"
    assert run["model_name"] == "configured-model"
    assert run["status"] == "failed"


def test_run_api_rejects_unsupported_provider(client):
    response = client.post(
        "/runs",
        json={
            "dataset_id": "00000000-0000-0000-0000-000000000001",
            "provider": "other",
        },
    )

    assert response.status_code == 422


def test_run_api_accepts_groq_without_credentials_fallback(client, monkeypatch):
    from app.providers.groq import GroqProvider

    monkeypatch.setattr(
        "app.services.evaluation.get_provider",
        lambda name: GroqProvider(api_key=None, model_name="openai/gpt-oss-20b"),
    )
    dataset = create_dataset(client, cases=[
        {"name": "provider failure", "input_data": {"prompt": "hello"}}
    ])

    response = client.post(
        "/runs",
        json={"dataset_id": dataset.json()["id"], "provider": "groq"},
    )

    assert response.status_code == 201
    run = response.json()
    assert run["provider"] == "groq"
    assert run["model_name"] == "openai/gpt-oss-20b"
    assert run["status"] == "failed"
    assert run["cases"][0]["status"] == "failed"
    assert "GROQ_API_KEY" in run["cases"][0]["error_message"]


def test_dataset_and_case_missing_results_return_not_found(client):
    missing_dataset = client.get("/datasets/00000000-0000-0000-0000-000000000001")
    missing_run = client.get("/runs/00000000-0000-0000-0000-000000000001")
    missing_case = client.get(
        "/runs/00000000-0000-0000-0000-000000000001/cases/00000000-0000-0000-0000-000000000002"
    )

    assert missing_dataset.status_code == 404
    assert missing_run.status_code == 404
    assert missing_case.status_code == 404
