import json

from fastapi.testclient import TestClient

from app.core.config import Settings


def upload(client: TestClient, file_name: str, content: str, *, data=None, headers=None):
    return client.post(
        "/datasets/import/preview",
        files={"file": (file_name, content.encode(), "application/octet-stream")},
        data=data,
        headers=headers,
    )


def import_file(
    client: TestClient,
    file_name: str,
    content: str,
    *,
    name: str = "Imported",
    mapping: dict | None = None,
    policy: str = "reject",
    idempotency_key: str | None = None,
):
    data = {"name": name, "invalid_policy": policy}
    if mapping is not None:
        data["column_mapping"] = json.dumps(mapping)
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
    return client.post(
        "/datasets/import",
        files={"file": (file_name, content.encode(), "application/octet-stream")},
        data=data,
        headers=headers,
    )


def test_jsonl_preview_partial_import_and_idempotency(client):
    content = (
        '{"case_id":"first","input_data":{"prompt":"hello"},"expected_output":"hello"}\n'
        '{"name":"second","input_data":"world","expect_valid_json":true}\n'
        '{"case_id":"first","input_data":{"prompt":"duplicate"}}\n'
        '{"name":"invalid","expected_output":"missing input"}\n'
    )
    preview = upload(client, "cases.jsonl", content)
    assert preview.status_code == 200
    assert preview.json()["total_rows"] == 4
    assert preview.json()["valid_cases"] == 2
    assert preview.json()["invalid_cases"] == 2
    assert preview.json()["missing_expected_outputs"] == 1
    assert preview.json()["duplicate_identifiers"] == 1
    assert [issue["row"] for issue in preview.json()["errors"]] == [3, 4]

    rejected = import_file(client, "cases.jsonl", content)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["details"]["report"]["invalid_cases"] == 2

    created = import_file(
        client,
        "cases.jsonl",
        content,
        policy="valid_only",
        idempotency_key="jsonl-request-1",
    )
    assert created.status_code == 201
    body = created.json()
    assert body["created_cases"] == 2
    assert body["rejected_cases"] == 2
    assert body["dataset"]["source_file_name"] == "cases.jsonl"
    assert body["dataset"]["import_status"] == "partial"
    assert body["dataset"]["cases"][1]["input_data"] == {"prompt": "world"}
    assert body["dataset"]["cases"][1]["expected_json"] is True
    assert body["dataset"]["cases"][1]["expected_output"] is None

    retried = import_file(
        client,
        "cases.jsonl",
        content,
        name="different name ignored on retry",
        policy="valid_only",
        idempotency_key="jsonl-request-1",
    )
    assert retried.status_code == 201
    assert retried.json()["duplicate_submission"] is True
    assert retried.json()["created_cases"] == 0


def test_json_import_accepts_cases_array_expected_object_and_metadata(client):
    content = json.dumps(
        {
            "cases": [
                {
                    "name": "json response",
                    "input_data": {"prompt": "return json"},
                    "expected_output": {"status": "ok"},
                    "expect_valid_json": True,
                    "metadata": {"source": "fixture"},
                },
                {"input_data": ["supported", "value"], "reference_keywords": ["supported"]},
            ]
        }
    )
    response = import_file(client, "data.json", content)
    assert response.status_code == 201
    cases = response.json()["dataset"]["cases"]
    assert cases[0]["expected_output"] == '{"status":"ok"}'
    assert cases[0]["expected_json"] is True
    assert cases[0]["metadata"] == {"source": "fixture"}
    assert cases[1]["name"] == "case_000002"
    assert cases[1]["input_data"] == {"value": ["supported", "value"]}


def test_csv_column_mapping_and_batch_insert(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.dataset_import.get_settings",
        lambda: Settings(dataset_import_batch_size=2),
    )
    content = "case_id,prompt,answer,keywords,json_ok\none,hello,hello,\"hello,world\",false\ntwo,2+3,5,5,true\nthree,test,,,\n"
    mapping = {
        "case_id": "case_id",
        "input_data": "prompt",
        "expected_output": "answer",
        "reference_keywords": "keywords",
        "expect_valid_json": "json_ok",
    }
    preview = upload(
        client,
        "cases.csv",
        content,
        data={"column_mapping": json.dumps(mapping)},
    )
    assert preview.status_code == 200
    assert preview.json()["columns"] == ["case_id", "prompt", "answer", "keywords", "json_ok"]
    assert preview.json()["valid_cases"] == 3
    imported = import_file(client, "cases.csv", content, mapping=mapping)
    assert imported.status_code == 201
    cases = imported.json()["dataset"]["cases"]
    assert imported.json()["created_cases"] == 3
    assert cases[0]["reference_keywords"] == ["hello", "world"]
    assert cases[1]["expected_json"] is True
    assert cases[2]["expected_output"] is None


def test_malformed_files_and_case_limits_are_reported(client, monkeypatch):
    malformed = upload(client, "broken.json", '{"cases": [')
    assert malformed.status_code == 422
    missing_cases = upload(client, "wrong-shape.json", '{"not_cases": []}')
    assert missing_cases.status_code == 422

    monkeypatch.setattr(
        "app.services.dataset_import.get_settings",
        lambda: Settings(dataset_import_max_cases=2),
    )
    content = "\n".join(
        json.dumps({"input_data": {"prompt": f"case {index}"}})
        for index in range(3)
    )
    limited = upload(client, "large.jsonl", content)
    assert limited.status_code == 200
    assert limited.json()["valid_cases"] == 2
    assert limited.json()["invalid_cases"] == 1
    assert "2-case limit" in limited.json()["errors"][0]["message"]


def test_large_jsonl_import_inserts_many_cases_and_preserves_positions(client):
    row_count = 1000
    content = "\n".join(
        json.dumps({"input_data": {"prompt": f"case {index}"}})
        for index in range(row_count)
    )
    response = import_file(client, "large.jsonl", content)
    assert response.status_code == 201
    dataset = response.json()["dataset"]
    assert response.json()["created_cases"] == row_count
    assert len(dataset["cases"]) == row_count
    assert dataset["cases"][0]["position"] == 0
    assert dataset["cases"][-1]["position"] == row_count - 1


def test_duplicate_content_is_rejected_even_with_a_new_submission_key(client):
    content = '{"name":"one","input_data":{"prompt":"hello"}}'
    first = import_file(client, "one.jsonl", content, idempotency_key="key-one")
    second = import_file(client, "renamed.jsonl", content, idempotency_key="key-two")
    assert first.status_code == 201
    assert second.status_code == 409


def test_validate_persisted_dataset_reports_duplicates_and_shape(client, db_session):
    from app.models.evaluation import DatasetCase, EvaluationDataset

    dataset = EvaluationDataset(name="validate me")
    dataset.cases = [
        DatasetCase(name="same", position=0, input_data={"prompt": "one"}),
        DatasetCase(name="same", position=1, input_data={"prompt": "two"}),
    ]
    db_session.add(dataset)
    db_session.commit()
    dataset_id = dataset.id
    response = client.post(f"/datasets/{dataset_id}/validate")
    assert response.status_code == 200
    assert response.json()["invalid_cases"] == 1
    assert response.json()["duplicate_identifiers"] == 1
