import json

import httpx

from pydantic import SecretStr

from app.core.config import Settings
from app.services import project_evaluation


def install_project_http(monkeypatch, handler):
    settings = Settings(
        project_allowed_hosts="api.example.test",
        project_allowed_endpoints="https://api.example.test/infer",
        project_auth_env_vars="RELI_TEST_PROJECT_TOKEN",
        project_auth_tokens_json=SecretStr('{"RELI_TEST_PROJECT_TOKEN":"top-secret-value"}'),
        project_max_concurrency=3,
        project_requests_per_second=100,
        project_max_retries=0,
        project_http_timeout_seconds=2,
    )
    monkeypatch.setattr(project_evaluation, "get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.api.projects.validate_endpoint_url",
        lambda url: ("api.example.test", "93.184.216.34"),
    )
    monkeypatch.setattr(
        project_evaluation,
        "validate_endpoint_url",
        lambda url: ("api.example.test", "93.184.216.34"),
    )
    monkeypatch.setattr(
        project_evaluation,
        "PinnedIPTransport",
        lambda hostname, address: httpx.MockTransport(handler),
    )


def create_project(client, *, auth_env_var=None):
    return client.post(
        "/projects",
        json={
            "name": "Fixture AI",
            "endpoint_url": "https://api.example.test/infer",
            "request_template": {"prompt": "{{input_data.prompt}}"},
            "response_path": "result.answer",
            "auth_env_var": auth_env_var,
        },
    )


def test_project_evaluation_uses_actual_mocked_endpoint_and_persists_results(
    client, monkeypatch
):
    seen_headers = []

    def handler(request: httpx.Request):
        seen_headers.append(request.headers.get("authorization"))
        prompt = json.loads(request.content)["prompt"]
        return httpx.Response(200, json={"result": {"answer": prompt}})

    install_project_http(monkeypatch, handler)
    project = create_project(client, auth_env_var="RELI_TEST_PROJECT_TOKEN").json()
    dataset = client.post(
        "/datasets/import",
        files={
            "file": (
                "project-cases.jsonl",
                (
                    '{"name":"echo one","input_data":{"prompt":"READY"},'
                    '"expected_output":"READY","reference_keywords":["READY"]}\n'
                    '{"name":"echo two","input_data":{"prompt":"done"},'
                    '"expected_output":"done"}\n'
                ),
                "application/x-ndjson",
            )
        },
        data={"name": "project fixture data"},
        headers={"Idempotency-Key": "project-fixture-import"},
    ).json()["dataset"]

    accepted = client.post(
        "/projects/evaluations",
        json={"project_id": project["id"], "dataset_id": dataset["id"]},
    )

    assert accepted.status_code == 202
    run_id = accepted.json()["run_id"]
    run = client.get(f"/runs/{run_id}").json()
    assert run["project_id"] == project["id"]
    assert run["provider"] == "project"
    assert run["status"] == "completed"
    assert run["metrics"]["exact_match"] == {
        "value": 1.0,
        "available_cases": 2,
        "total_cases": 2,
    }
    assert [case["actual_output"] for case in run["cases"]] == ["READY", "done"]
    traces = client.get(f"/runs/{run_id}/traces").json()
    assert len(traces) == 2
    assert all(
        trace["trace_metadata"]
        == {
            "http_status_code": 200,
            "response_body": {"result": {"answer": "READY" if index == 0 else "done"}},
        }
        for index, trace in enumerate(traces)
    )
    assert all(isinstance(trace["latency_ms"], int) for trace in traces)
    assert seen_headers == ["Bearer top-secret-value"] * 2
    assert "top-secret-value" not in json.dumps(run)
    assert client.get(f"/runs/{run_id}/progress").json()["completed_cases"] == 2


def test_project_http_failures_and_malformed_outputs_are_recorded(client, monkeypatch):
    def handler(request: httpx.Request):
        prompt = json.loads(request.content)["prompt"]
        if prompt == "unauthorized":
            return httpx.Response(401)
        if prompt == "rate-limited":
            return httpx.Response(429)
        if prompt == "redirect":
            return httpx.Response(302, headers={"Location": "https://other.example.test"})
        if prompt == "malformed":
            return httpx.Response(200, text="not-json")
        if prompt == "timeout":
            raise httpx.ReadTimeout("upstream timeout", request=request)
        return httpx.Response(200, json={"result": {"answer": prompt}})

    install_project_http(monkeypatch, handler)
    project = create_project(client).json()
    dataset = client.post(
        "/datasets",
        json={
            "name": "failure fixture data",
            "cases": [
                {"name": prompt, "input_data": {"prompt": prompt}}
                for prompt in ("unauthorized", "rate-limited", "redirect", "malformed", "timeout")
            ],
        },
    ).json()
    run_id = client.post(
        "/projects/evaluations",
        json={"project_id": project["id"], "dataset_id": dataset["id"]},
    ).json()["run_id"]
    run = client.get(f"/runs/{run_id}").json()
    traces = client.get(f"/runs/{run_id}/traces").json()

    assert run["status"] == "failed"
    assert len(run["cases"]) == 5
    assert all(case["metrics"]["exact_match"]["available"] is False for case in run["cases"])
    categories = {trace["error_type"] for trace in traces}
    assert categories == {"authentication", "rate_limit", "provider_error", "invalid_output", "timeout"}
    by_category = {trace["error_type"]: trace for trace in traces}
    assert by_category["authentication"]["trace_metadata"] == {"http_status_code": 401}
    assert by_category["rate_limit"]["trace_metadata"] == {"http_status_code": 429}
    assert by_category["provider_error"]["trace_metadata"] == {"http_status_code": 302}


def test_project_endpoint_validation_rejects_restricted_and_unlisted_hosts(monkeypatch):
    settings = Settings(
        project_allowed_hosts="api.example.test",
        project_allowed_endpoints="https://api.example.test/infer",
    )
    monkeypatch.setattr(project_evaluation, "get_settings", lambda: settings)
    monkeypatch.setattr(
        project_evaluation,
        "resolve_public_ips",
        lambda host: ["127.0.0.1"],
    )
    assert "HTTPS" in str(
        _validation_error(lambda: project_evaluation.validate_endpoint_url("http://api.example.test/infer"))
    )
    assert "allowlisted" in str(
        _validation_error(lambda: project_evaluation.validate_endpoint_url("https://other.example.test/infer"))
    )
    assert "restricted" in str(
        _validation_error(lambda: project_evaluation.validate_endpoint_url("https://api.example.test/infer"))
    )


def _validation_error(operation):
    try:
        operation()
    except ValueError as exc:
        return exc
    raise AssertionError("Expected endpoint validation to fail")


def test_project_registration_does_not_store_or_return_credentials(client, monkeypatch):
    install_project_http(monkeypatch, lambda request: httpx.Response(200, json={"result": {"answer": "ok"}}))
    project = create_project(client, auth_env_var="RELI_TEST_PROJECT_TOKEN")
    assert project.status_code == 201
    assert project.json()["auth_env_var"] == "RELI_TEST_PROJECT_TOKEN"
    assert "top-secret-value" not in project.text


def install_local_knowledgeops(monkeypatch, handler):
    endpoint = "http://knowledgeops-backend-1:8000/ask"
    settings = Settings(
        project_allowed_local_docker_endpoints=endpoint,
        project_local_docker_network_cidr="172.18.0.0/16",
        project_max_concurrency=2,
        project_requests_per_second=100,
        project_max_retries=0,
        project_http_timeout_seconds=2,
    )
    monkeypatch.setattr(project_evaluation, "get_settings", lambda: settings)
    monkeypatch.setattr(
        project_evaluation,
        "resolve_local_docker_ips",
        lambda hostname, port: ["172.18.0.3"],
    )
    monkeypatch.setattr(
        project_evaluation,
        "PinnedIPTransport",
        lambda hostname, address: httpx.MockTransport(handler),
    )


def test_knowledgeops_target_maps_query_extracts_answer_and_persists_response(
    client, monkeypatch
):
    seen_requests = []
    response_body = {
        "question": "What technologies?",
        "answer": "FastAPI, Docker, and Qdrant.",
        "model": "fixture",
        "request_id": "fixture-request",
        "retrieved_chunks": 2,
        "candidate_count": 12,
        "reranker": "fixture-reranker",
        "latency": {"total_ms": 31.5},
        "citations": [{"citation": 1, "filename": "architecture.pdf"}],
        "retrieved_sources": [{"text": "FastAPI, Docker, and Qdrant."}],
    }

    def handler(request: httpx.Request):
        seen_requests.append((request.method, request.url.path, json.loads(request.content)))
        return httpx.Response(200, json=response_body)

    install_local_knowledgeops(monkeypatch, handler)
    project = client.post(
        "/projects",
        json={
            "name": "KnowledgeOps",
            "endpoint_url": "http://knowledgeops-backend-1:8000/ask",
            "request_template": {
                "query": "{{input_data.prompt}}",
                "limit": 5,
                "candidate_limit": 12,
            },
            "response_path": "answer",
        },
    )
    assert project.status_code == 201
    dataset = client.post(
        "/datasets",
        json={
            "name": "KnowledgeOps evaluation",
            "cases": [
                {
                    "name": "architecture technologies",
                    "input_data": {
                        "prompt": "What technologies?",
                        "metadata": {"source": "fixture"},
                    },
                    "expected_output": "FastAPI, Docker, and Qdrant.",
                }
            ],
        },
    ).json()

    accepted = client.post(
        "/projects/evaluations",
        json={"project_id": project.json()["id"], "dataset_id": dataset["id"]},
    )
    assert accepted.status_code == 202
    run_id = accepted.json()["run_id"]
    run = client.get(f"/runs/{run_id}").json()
    traces = client.get(f"/runs/{run_id}/traces").json()

    assert run["status"] == "completed"
    assert run["cases"][0]["actual_output"] == response_body["answer"]
    assert run["cases"][0]["metrics"]["exact_match"] == {
        "value": 1.0,
        "available": True,
    }
    assert run["cases"][0]["metrics"]["reference_keyword_coverage"] == {
        "value": None,
        "available": False,
    }
    assert run["metrics"]["exact_match"]["value"] == 1.0
    assert seen_requests == [
        (
            "POST",
            "/ask",
            {
                "query": "What technologies?",
                "limit": 5,
                "candidate_limit": 12,
            },
        )
    ]
    assert traces[0]["trace_metadata"]["http_status_code"] == 200
    assert traces[0]["trace_metadata"]["response_body"] == response_body
    assert isinstance(traces[0]["latency_ms"], int)


def test_knowledgeops_http_failure_is_persisted_without_answer_substitution(
    client, monkeypatch
):
    install_local_knowledgeops(
        monkeypatch, lambda request: httpx.Response(503, json={"detail": "unavailable"})
    )
    project = client.post(
        "/projects",
        json={
            "name": "KnowledgeOps unavailable",
            "endpoint_url": "http://knowledgeops-backend-1:8000/ask",
            "request_template": {
                "query": "{{input_data.prompt}}",
                "limit": 5,
                "candidate_limit": 12,
            },
            "response_path": "answer",
        },
    ).json()
    dataset = client.post(
        "/datasets",
        json={
            "name": "KnowledgeOps failing evaluation",
            "cases": [
                {
                    "name": "failed target",
                    "input_data": {"prompt": "Query"},
                    "expected_output": "Expected",
                }
            ],
        },
    ).json()

    run_id = client.post(
        "/projects/evaluations",
        json={"project_id": project["id"], "dataset_id": dataset["id"]},
    ).json()["run_id"]
    run = client.get(f"/runs/{run_id}").json()
    trace = client.get(f"/runs/{run_id}/traces").json()[0]

    assert run["status"] == "failed"
    assert run["cases"][0]["actual_output"] is None
    assert run["cases"][0]["metrics"]["exact_match"] == {
        "value": None,
        "available": False,
    }
    assert trace["status"] == "failed"
    assert trace["trace_metadata"] == {"http_status_code": 503}
    assert isinstance(trace["latency_ms"], int)


def test_local_docker_target_requires_exact_endpoint_and_approved_network(monkeypatch):
    settings = Settings(
        project_allowed_local_docker_endpoints=(
            "http://knowledgeops-backend-1:8000/ask"
        ),
        project_local_docker_network_cidr="172.18.0.0/16",
    )
    monkeypatch.setattr(project_evaluation, "get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.services.project_evaluation.socket.getaddrinfo",
        lambda hostname, port, **kwargs: [
            (2, 1, 6, "", ("172.19.0.3", port))
        ],
    )

    error = _validation_error(
        lambda: project_evaluation.validate_endpoint_url(
            "http://knowledgeops-backend-1:8000/ask"
        )
    )
    assert "approved private network" in str(error)
    assert "HTTP" in str(
        _validation_error(
            lambda: project_evaluation.validate_endpoint_url(
                "http://knowledgeops-backend-1:8001/ask"
            )
        )
    )
    assert "HTTPS URL" in str(
        _validation_error(
            lambda: project_evaluation.validate_endpoint_url(
                "http://127.0.0.1:8000/ask"
            )
        )
    )


def test_project_authentication_failures_do_not_expose_secrets(client, monkeypatch, caplog):
    install_project_http(monkeypatch, lambda request: httpx.Response(401))
    project = create_project(client, auth_env_var="RELI_TEST_PROJECT_TOKEN").json()
    dataset = client.post(
        "/datasets",
        json={
            "name": "authenticated target",
            "cases": [{"name": "one", "input_data": {"prompt": "hello"}}],
        },
    ).json()

    run_id = client.post(
        "/projects/evaluations",
        json={"project_id": project["id"], "dataset_id": dataset["id"]},
    ).json()["run_id"]
    run = client.get(f"/runs/{run_id}").text
    traces = client.get(f"/runs/{run_id}/traces").text

    assert "top-secret-value" not in run
    assert "top-secret-value" not in traces
    assert "top-secret-value" not in caplog.text
