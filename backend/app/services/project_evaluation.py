import ipaddress
import json
import logging
import re
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.core.config import get_settings
from app.models.evaluation import (
    AIProject,
    EvaluationCase,
    EvaluationCaseStatus,
    EvaluationDataset,
    EvaluationRun,
    EvaluationRunStatus,
    ExecutionTrace,
    ExecutionTraceStatus,
)
from app.providers.base import InvalidProviderOutput
from app.services.errors import classify_execution_error, sanitized_error_details, sanitize_error_message
from app.services.metrics import aggregate_metrics, evaluate_metrics, unavailable_metrics

logger = logging.getLogger("reli.project_evaluation")
PLACEHOLDER = re.compile(r"^\{\{input_data((?:\.[A-Za-z0-9_-]+|\[\d+\])*)\}\}$")


class ProjectRequestFailure(RuntimeError):
    def __init__(
        self,
        message: str,
        category: str,
        status_code: int | None = None,
        latency_ms: int | None = None,
    ):
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.latency_ms = latency_ms


@dataclass(frozen=True)
class ProjectResponse:
    output: str
    status_code: int
    latency_ms: int
    response_body: Any


def canonical_local_docker_endpoint(endpoint_url: str) -> str:
    try:
        parts = urlsplit(endpoint_url)
        hostname = (parts.hostname or "").encode("idna").decode("ascii").casefold()
        port = parts.port
    except (ValueError, UnicodeError):
        return ""
    if (
        parts.scheme != "http"
        or not hostname
        or port is None
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or hostname.endswith((".localhost", ".local", ".internal"))
    ):
        return ""
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        return ""
    return f"http://{hostname}:{port}{parts.path or '/'}"


def allowed_local_docker_endpoints() -> set[str]:
    return {
        endpoint
        for configured in get_settings().project_allowed_local_docker_endpoints.split(",")
        if (endpoint := canonical_local_docker_endpoint(configured.strip()))
    }


def allowed_hosts() -> set[str]:
    return {
        host.strip().encode("idna").decode("ascii").casefold()
        for host in get_settings().project_allowed_hosts.split(",")
        if host.strip()
    }


def canonical_endpoint(endpoint_url: str) -> str:
    parts = urlsplit(endpoint_url)
    if parts.scheme != "https" or not parts.hostname or parts.port not in (None, 443):
        return ""
    host = parts.hostname.encode("idna").decode("ascii").casefold()
    return f"https://{host}{parts.path or '/'}"


def allowed_endpoints() -> set[str]:
    return {
        endpoint
        for configured in get_settings().project_allowed_endpoints.split(",")
        if (endpoint := canonical_endpoint(configured.strip()))
    }


def allowed_auth_env_vars() -> set[str]:
    return {
        variable.strip()
        for variable in get_settings().project_auth_env_vars.split(",")
        if variable.strip()
    }


def resolve_public_ips(host: str) -> list[str]:
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Project endpoint hostname could not be resolved") from exc
    addresses = sorted({record[4][0] for record in records})
    if not addresses:
        raise ValueError("Project endpoint hostname has no address records")
    parsed = [ipaddress.ip_address(address) for address in addresses]
    if any(not address.is_global for address in parsed):
        raise ValueError("Project endpoint resolves to a restricted network address")
    return [str(address) for address in parsed]


def resolve_local_docker_ips(host: str, port: int) -> list[str]:
    configured_network = get_settings().project_local_docker_network_cidr.strip()
    if not configured_network:
        raise ValueError("The local Docker target network is not configured")
    try:
        network = ipaddress.ip_network(configured_network, strict=False)
    except ValueError as exc:
        raise ValueError("The local Docker target network CIDR is invalid") from exc
    if network.version != 4:
        raise ValueError("The local Docker target network must be an IPv4 CIDR")
    try:
        records = socket.getaddrinfo(host, port, family=socket.AF_INET, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Local Docker target hostname could not be resolved") from exc
    addresses = sorted({record[4][0] for record in records})
    if not addresses:
        raise ValueError("Local Docker target hostname has no address records")
    parsed = [ipaddress.ip_address(address) for address in addresses]
    if any(
        address not in network
        or not address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        for address in parsed
    ):
        raise ValueError("Local Docker target resolves outside its approved private network")
    return [str(address) for address in parsed]


def validate_endpoint_url(endpoint_url: str) -> tuple[str, str]:
    try:
        parts = urlsplit(endpoint_url)
        host = (parts.hostname or "").encode("idna").decode("ascii").casefold()
        port = parts.port
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Project endpoint URL is invalid") from exc
    local_endpoint = canonical_local_docker_endpoint(endpoint_url)
    if local_endpoint and local_endpoint in allowed_local_docker_endpoints():
        if port is None:
            raise ValueError("Local Docker target must include its explicitly authorized port")
        addresses = resolve_local_docker_ips(host, port)
        return host, addresses[0]
    if (
        parts.scheme != "https"
        or not host
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or port not in (None, 443)
        or host.endswith((".localhost", ".local", ".internal"))
    ):
        raise ValueError(
            "Project endpoint must be an allowlisted HTTPS URL or an explicitly authorized local Docker endpoint"
        )
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("Project endpoint must use an allowlisted DNS hostname, not an IP address")
    if host not in allowed_hosts():
        raise ValueError("Project endpoint hostname is not explicitly allowlisted")
    if canonical_endpoint(endpoint_url) not in allowed_endpoints():
        raise ValueError("Project endpoint URL is not explicitly authorized")
    ips = resolve_public_ips(host)
    if any(not ipaddress.ip_address(address).is_global for address in ips):
        raise ValueError("Project endpoint resolves to a restricted network address")
    return host, ips[0]


class PinnedIPTransport(httpx.BaseTransport):
    def __init__(self, hostname: str, address: str):
        self.hostname = hostname
        self.address = address
        self.inner = httpx.HTTPTransport(retries=0, trust_env=False)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        port = request.url.port or 443
        host_header = self.hostname if port == 443 else f"{self.hostname}:{port}"
        headers = dict(request.headers)
        headers["host"] = host_header
        pinned_url = request.url.copy_with(host=self.address)
        pinned_request = httpx.Request(
            request.method,
            pinned_url,
            headers=headers,
            content=request.read(),
            extensions={**request.extensions, "sni_hostname": self.hostname},
        )
        return self.inner.handle_request(pinned_request)

    def close(self) -> None:
        self.inner.close()


def _render_template(value: Any, input_data: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _render_template(item, input_data) for key, item in value.items()}
    if isinstance(value, list):
        return [_render_template(item, input_data) for item in value]
    if not isinstance(value, str):
        return value
    match = PLACEHOLDER.fullmatch(value)
    if not match:
        return value
    result: Any = input_data
    path = match.group(1)
    for token in re.findall(r"\.([A-Za-z0-9_-]+)|\[(\d+)\]", path):
        key = token[0] or token[1]
        try:
            result = result[int(key)] if isinstance(result, list) else result[key]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"Request template input path is missing: {value}") from exc
    return result


def _extract_response(payload: Any, response_path: str) -> Any:
    if response_path == "$":
        return payload
    current = payload
    for token in response_path.replace("[", ".").replace("]", "").split("."):
        if not token:
            continue
        try:
            current = current[int(token)] if isinstance(current, list) else current[token]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise InvalidProviderOutput("Project response did not contain the configured response field") from exc
    return current


def _response_text(response: httpx.Response, response_path: str) -> tuple[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        if response_path == "text":
            return response.text, response.text
        raise InvalidProviderOutput("Project returned a malformed JSON response")
    if response_path == "text":
        extracted = response.text
    else:
        extracted = _extract_response(payload, response_path)
    if isinstance(extracted, str):
        return extracted, payload
    output = (
        extracted
        if isinstance(extracted, str)
        else json.dumps(extracted, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return output, payload


def _auth_header(project: AIProject) -> dict[str, str]:
    if not project.auth_env_var:
        return {}
    if project.auth_env_var not in allowed_auth_env_vars():
        raise ProjectRequestFailure(
            "Project authentication variable is not authorized by backend configuration",
            "authentication",
        )
    auth_tokens = get_settings().project_auth_tokens_json
    try:
        token_map = json.loads(auth_tokens.get_secret_value()) if auth_tokens else {}
    except json.JSONDecodeError as exc:
        raise ProjectRequestFailure(
            "Backend project authentication configuration is invalid",
            "authentication",
        ) from exc
    secret = token_map.get(project.auth_env_var) if isinstance(token_map, dict) else None
    if not isinstance(secret, str) or not secret:
        raise ProjectRequestFailure(
            f"Required backend authentication setting {project.auth_env_var} is not configured",
            "authentication",
        )
    credential = f"{project.auth_scheme} {secret}".strip()
    return {project.auth_header: credential}


def _request_once(
    project: AIProject,
    input_data: dict[str, Any],
    *,
    transport: httpx.BaseTransport | None = None,
) -> ProjectResponse:
    hostname, pinned_ip = validate_endpoint_url(project.endpoint_url)
    request_body = _render_template(project.request_template, input_data)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    headers.update(_auth_header(project))
    client_transport = transport or PinnedIPTransport(hostname, pinned_ip)
    started_at = time.perf_counter()
    try:
        with httpx.Client(
            transport=client_transport,
            timeout=get_settings().project_http_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = client.request(
                project.http_method,
                project.endpoint_url,
                headers=headers,
                json=request_body,
            )
    except httpx.TimeoutException as exc:
        latency_ms = max(0, round((time.perf_counter() - started_at) * 1000))
        raise ProjectRequestFailure(
            "Project endpoint request timed out", "timeout", latency_ms=latency_ms
        ) from exc
    except httpx.RequestError as exc:
        latency_ms = max(0, round((time.perf_counter() - started_at) * 1000))
        raise ProjectRequestFailure(
            "Project endpoint request failed", "provider_error", latency_ms=latency_ms
        ) from exc
    latency_ms = max(0, round((time.perf_counter() - started_at) * 1000))
    if 300 <= response.status_code < 400:
        raise ProjectRequestFailure(
            "Project endpoint redirects are not followed",
            "provider_error",
            response.status_code,
            latency_ms,
        )
    if response.status_code in (401, 403):
        raise ProjectRequestFailure(
            f"Project endpoint authentication failed (HTTP {response.status_code})",
            "authentication",
            response.status_code,
            latency_ms,
        )
    if response.status_code == 429:
        raise ProjectRequestFailure(
            "Project endpoint rate limit exceeded", "rate_limit", 429, latency_ms
        )
    if response.is_error:
        raise ProjectRequestFailure(
            f"Project endpoint returned HTTP {response.status_code}",
            "provider_error",
            response.status_code,
            latency_ms,
        )
    try:
        output, response_body = _response_text(response, project.response_path)
        return ProjectResponse(
            output, response.status_code, latency_ms, response_body
        )
    except InvalidProviderOutput as exc:
        exc.status_code = response.status_code
        exc.latency_ms = latency_ms
        raise


def request_project(
    project: AIProject,
    input_data: dict[str, Any],
    *,
    transport: httpx.BaseTransport | None = None,
    limiter: "RequestRateLimiter | None" = None,
) -> ProjectResponse:
    settings = get_settings()
    total_latency_ms = 0
    has_latency = False
    for attempt in range(settings.project_max_retries + 1):
        if limiter is not None:
            limiter.wait()
        try:
            with _PROJECT_CONCURRENCY:
                response = _request_once(project, input_data, transport=transport)
                return ProjectResponse(
                    response.output,
                    response.status_code,
                    total_latency_ms + response.latency_ms,
                    response.response_body,
                )
        except ProjectRequestFailure as exc:
            if exc.latency_ms is not None:
                total_latency_ms += exc.latency_ms
                has_latency = True
            if attempt >= settings.project_max_retries or exc.category not in {"timeout", "rate_limit", "provider_error"}:
                exc.latency_ms = total_latency_ms if has_latency else None
                raise
            time.sleep(min(0.25 * (2**attempt), 1.0))
    raise RuntimeError("Project request retry loop exited unexpectedly")


class RequestRateLimiter:
    def __init__(self, requests_per_second: int):
        self.interval = 1 / requests_per_second
        self.lock = threading.Lock()
        self.next_request_at = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_request_at - now)
            self.next_request_at = max(now, self.next_request_at) + self.interval
        if delay:
            time.sleep(delay)


_PROJECT_CONCURRENCY = threading.BoundedSemaphore(
    get_settings().project_max_concurrency
)


def execute_project_evaluation(
    bind: Engine | Connection,
    run_id: uuid.UUID,
    project_id: uuid.UUID,
    request_id: str | None,
) -> None:
    factory = sessionmaker(bind=bind, autoflush=False, expire_on_commit=False)
    with factory() as db:
        _execute_project_evaluation(db, run_id, project_id, request_id)


def _execute_project_evaluation(
    db: Session,
    run_id: uuid.UUID,
    project_id: uuid.UUID,
    request_id: str | None,
) -> None:
    run = db.scalar(
        select(EvaluationRun)
        .where(EvaluationRun.id == run_id)
        .options(selectinload(EvaluationRun.dataset).selectinload(EvaluationDataset.cases))
    )
    project = db.get(AIProject, project_id)
    if run is None or project is None or run.dataset is None:
        logger.error("project evaluation lost its persisted run, project, or dataset", extra={"run_id": str(run_id)})
        return

    run.status = EvaluationRunStatus.RUNNING
    run.started_at = datetime.now(timezone.utc)
    dataset_cases = list(run.dataset.cases)
    evaluation_cases: list[EvaluationCase] = []
    traces: list[ExecutionTrace] = []
    for dataset_case in dataset_cases:
        case = EvaluationCase(
            run_id=run.id,
            dataset_case_id=dataset_case.id,
            name=dataset_case.name,
            status=EvaluationCaseStatus.RUNNING,
            input_data=dataset_case.input_data,
            expected_output=dataset_case.expected_output,
            expected_json=dataset_case.expected_json,
            reference_keywords=dataset_case.reference_keywords,
        )
        db.add(case)
        db.flush()
        trace = ExecutionTrace(
            run_id=run.id,
            case_id=case.id,
            request_id=request_id,
            operation_name="project.case",
            status=ExecutionTraceStatus.RUNNING,
            provider="project",
            model_name=project.name,
            started_at=datetime.now(timezone.utc),
        )
        db.add(trace)
        evaluation_cases.append(case)
        traces.append(trace)
    db.commit()

    failed_cases = 0
    metrics_by_case: list[dict[str, Any]] = []
    limiter = RequestRateLimiter(get_settings().project_requests_per_second)
    try:
        with ThreadPoolExecutor(max_workers=get_settings().project_max_concurrency) as executor:
            future_cases = {}
            for case, trace in zip(evaluation_cases, traces, strict=True):
                future = executor.submit(request_project, project, case.input_data, limiter=limiter)
                future_cases[future] = (case, trace)
            for future in as_completed(future_cases):
                case, trace = future_cases[future]
                completed_at = datetime.now(timezone.utc)
                try:
                    response = future.result()
                    case.actual_output = response.output
                    case.status = EvaluationCaseStatus.COMPLETED
                    case.metrics = evaluate_metrics(
                        response.output,
                        expected_output=case.expected_output,
                        expected_json=case.expected_json,
                        reference_keywords=case.reference_keywords,
                    )
                    case.score = case.metrics["exact_match"]["value"]
                    trace.status = ExecutionTraceStatus.SUCCEEDED
                    trace.trace_metadata = {
                        "http_status_code": response.status_code,
                        "response_body": response.response_body,
                    }
                    trace.latency_ms = response.latency_ms
                except Exception as exc:
                    failed_cases += 1
                    category = getattr(exc, "category", classify_execution_error(exc))
                    safe_message = sanitize_error_message(str(exc) or type(exc).__name__)
                    case.status = EvaluationCaseStatus.FAILED
                    case.error_message = safe_message
                    case.metrics = unavailable_metrics()
                    trace.status = ExecutionTraceStatus.FAILED
                    trace.error_type = category
                    trace.error_message = safe_message
                    trace.error_details = sanitized_error_details(exc, category)
                    status_code = getattr(exc, "status_code", None)
                    trace.trace_metadata = (
                        {"http_status_code": status_code} if status_code is not None else None
                    )
                    trace.latency_ms = getattr(exc, "latency_ms", None)
                    logger.warning(
                        "project case failed",
                        extra={
                            "run_id": str(run.id),
                            "case_id": str(case.id),
                            "error_type": category,
                        },
                    )
                trace.completed_at = completed_at
                case.completed_at = completed_at
                metrics_by_case.append(case.metrics)
                db.commit()
        run.metrics = aggregate_metrics(metrics_by_case)
        run.status = EvaluationRunStatus.FAILED if failed_cases else EvaluationRunStatus.COMPLETED
        run.error_message = (
            f"{failed_cases} of {len(dataset_cases)} project case(s) failed" if failed_cases else None
        )
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        db.rollback()
        safe_message = sanitize_error_message(str(exc) or type(exc).__name__)
        logger.exception("project evaluation could not be completed", extra={"run_id": str(run.id)})
        run = db.get(EvaluationRun, run_id)
        if run is not None:
            run.status = EvaluationRunStatus.FAILED
            run.error_message = safe_message
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
