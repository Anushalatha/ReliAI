# ReliAI — AI Evaluation & Reliability Platform

ReliAI provides a FastAPI/PostgreSQL foundation, a deterministic evaluation engine, execution traces, run comparisons, configurable regression findings, bulk dataset import, explicitly authorized HTTP project evaluations, and a React operations frontend. Mock is the default provider and runs without API credentials. Groq is the recommended live provider. Together AI is inactive in the frontend and retained temporarily in the backend for compatibility.

## LLM providers

Set `LLM_PROVIDER=mock` or `LLM_PROVIDER=groq` to configure the backend default. Mock remains the default. The frontend offers Mock and Groq, with Groq recommended for real inference. Provider credentials are read only by the backend and must never be placed in frontend environment variables.

```env
LLM_PROVIDER=mock
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-20b
```

Groq's selected `openai/gpt-oss-20b` model is listed in its [hosted model catalog](https://console.groq.com/docs/models), at $0.075 per million input tokens and $0.30 per million output tokens at the time of writing. Groq requests use the OpenAI-compatible `https://api.groq.com/openai/v1/chat/completions` endpoint. Provider errors are recorded on the run/case and trace; failed live provider requests are never replaced with Mock responses. Token counts are stored only when supplied in provider responses.

Together AI selection is currently inactive in the frontend. Its backend adapter and settings are retained temporarily; the UI exposes only Mock and Groq.

For Docker Compose, copy `.env.example` to `.env`, add the key only to the backend-side `GROQ_API_KEY` setting, and restart the backend:

```powershell
docker compose up --build -d
```

## Run with Docker Compose

Docker Compose starts PostgreSQL, the API, and the production-built SPA frontend. The backend applies Alembic migrations before starting.

```powershell
docker compose up --build
```

The application is available at `http://localhost:5173`; the API is available at `http://localhost:8002`. Check `GET /health` for process health and `GET /health/ready` for database readiness.

To run migrations separately:

```powershell
docker compose run --rm backend alembic upgrade head
```

## Create and run an evaluation

Create a dataset with one or more cases. `input_data.prompt` is echoed by default; `expected_output`, `expected_json`, and `reference_keywords` enable the applicable deterministic metrics.

```powershell
$dataset = Invoke-RestMethod -Method Post -Uri http://localhost:8002/datasets `
  -ContentType "application/json" -Body '{"name":"demo","cases":[{"name":"echo","input_data":{"prompt":"hello"},"expected_output":"hello","reference_keywords":["hello"]}]}'

$run = Invoke-RestMethod -Method Post -Uri http://localhost:8002/runs `
  -ContentType "application/json" -Body (@{ dataset_id = $dataset.id; provider = "mock" } | ConvertTo-Json)
```

`POST /datasets/validate` validates a dataset payload without saving it. Use `GET /datasets`, `GET /datasets/{id}`, `GET /runs`, `GET /runs/{id}`, and `GET /runs/{id}/cases/{case_id}` to retrieve persisted data.

Per-case metrics contain `value` and `available`; unavailable measurements have a `null` value, not a fabricated zero. Run metric values are means across available cases and include `available_cases` and `total_cases`. Exact match is case-sensitive string equality. Keyword coverage is case-insensitive substring coverage. JSON validity measures whether the output parses as JSON when `expected_json` is true. Set `input_data.mock_output` to supply a deterministic custom response, or `input_data.mock_error` to simulate a failed case.

## Import reusable datasets

The Datasets page supports manual creation and multipart upload of `.csv`, `.json`, `.jsonl`, and `.ndjson` files. JSON files may contain either a top-level case array or an object with a `cases` array. JSONL/NDJSON contains one case object per non-empty line. Each case must have `input_data`; `name`/`case_id`, `expected_output`, `reference_keywords`, `expect_valid_json` (or `expected_json`), and a `metadata` object are optional. Missing names receive stable row-based names. Input objects are passed through as-is; JSON strings become `{"prompt": ...}`, and other JSON values are wrapped under `{"value": ...}` to preserve the existing provider input contract. Non-string expected outputs are stored as compact JSON text.

CSV requires a header and a user-selected input column. ReliAI provides a column mapping for case name/ID, expected output, comma-separated reference keywords, and JSON-validity expectation. A non-JSON input cell is treated as prompt text; a valid JSON cell is passed as JSON input. CSV cells with empty expected output are counted as missing, not filled in.

Default limits are **20 MiB per file**, **10,000 rows per dataset**, and **500 inserted cases per database batch**. Override them with `DATASET_IMPORT_MAX_BYTES`, `DATASET_IMPORT_MAX_CASES`, and `DATASET_IMPORT_BATCH_SIZE`. CSV and line-delimited JSON are streamed; JSON arrays are parsed incrementally. `POST /datasets/import/columns` reads CSV headers, `POST /datasets/import/preview` returns counts and row-numbered errors, and `POST /datasets/import` saves the file. The import endpoint accepts multipart fields `name`, optional `description`, `invalid_policy` (`reject` or `valid_only`), and optional JSON `column_mapping`. Use the `Idempotency-Key` header for safe retries; file content plus CSV mapping is also fingerprinted to prevent duplicate imports. Invalid rows are never silently skipped: choose valid-only import explicitly, and the persisted dataset keeps its source filename, import status, and validation report. Preview errors can be downloaded from the Datasets UI. Existing datasets remain unchanged. `POST /datasets/{dataset_id}/validate` checks a saved dataset again.

## Test an authorized AI project

Open **AI projects** in the UI to register an endpoint, select a saved dataset, and start a project evaluation. Project evaluations run asynchronously and create ordinary ReliAI runs, cases, metrics, and `project.case` traces. Progress is available at `GET /runs/{run_id}/progress`; full outputs and traces remain available from the existing run and observability endpoints. A successful response is evaluated with the same exact-match, JSON-validity, and keyword metrics as provider runs. Failed HTTP calls remain failed cases with unavailable quality metrics; ReliAI never substitutes Groq or Mock.

Remote project targets require an exact HTTPS hostname and full-endpoint allowlist:

```env
PROJECT_ALLOWED_HOSTS=api.example.com
PROJECT_ALLOWED_ENDPOINTS=https://api.example.com/v1/generate
```

Hosts and full endpoint URLs are exact allowlists; wildcards are not supported. Remote targets must use HTTPS on port 443, have no embedded credentials or query string, and resolve only to public IP addresses. Each request resolves and validates DNS again, connects to a pinned public IP while preserving TLS hostname verification, and does not follow redirects. Localhost, private/reserved networks, metadata addresses, IP-literal hosts, unlisted endpoints, and redirects are blocked.

### Local KnowledgeOps Docker target

The local KnowledgeOps Compose configuration defines service `backend`, with container port `8000` published as host port `8000`. Its active Compose project/network is `knowledgeops` / `knowledgeops_default`; the backend container is named `knowledgeops-backend-1`, and the inspected Docker network CIDR is `172.18.0.0/16`. ReliAI's backend joins that external network in addition to its own default network. From inside ReliAI, register this exact URL (do not use host `localhost`):

```text
http://knowledgeops-backend-1:8000/ask
```

The operator allowlist is scoped to the exact endpoint and Docker subnet:

```env
KNOWLEDGEOPS_DOCKER_NETWORK=knowledgeops_default
PROJECT_ALLOWED_LOCAL_DOCKER_ENDPOINTS=http://knowledgeops-backend-1:8000/ask
PROJECT_LOCAL_DOCKER_NETWORK_CIDR=172.18.0.0/16
```

The endpoint setting is exact: scheme, service hostname, port, and path must all match; query strings, credentials, IP literals, and redirects are not accepted. The runtime resolves the service name again for each request and pins the connection only when every resolved address is private and inside the configured network CIDR. No other private or localhost target is enabled. The external network must already exist (start KnowledgeOps with its Compose project first). If Docker assigns a different network name or subnet, configure the actual inspected values explicitly rather than widening the allowlist. HTTPS remote targets remain governed separately by `PROJECT_ALLOWED_HOSTS` and `PROJECT_ALLOWED_ENDPOINTS`.

KnowledgeOps `/ask` accepts `query`, `limit`, and `candidate_limit`. To evaluate it, create a ReliAI project with this JSON request template and response path:

```json
{
  "query": "{{input_data.prompt}}",
  "limit": 5,
  "candidate_limit": 12
}
```

Set the response extraction path to `answer`. Import each evaluation prompt under `input_data.prompt` and provide an `expected_output` for exact-match comparison. ReliAI stores the extracted answer as the case output and preserves the complete successful KnowledgeOps JSON response, HTTP status, and endpoint latency in the case trace. HTTP success alone does not count as a correct answer; exact-match is calculated against each case's expected output. Citation correctness and retrieval quality remain unavailable because ReliAI does not infer those metrics from returned citations or chunk counts.

The shared KnowledgeOps network and endpoint defaults are explicitly configured in Docker Compose and `.env.example`. The request timeout, concurrent workers, requests-per-second pacing, and retry count are also bounded by backend settings:

```env
PROJECT_HTTP_TIMEOUT_SECONDS=20
PROJECT_MAX_CONCURRENCY=8
PROJECT_REQUESTS_PER_SECOND=5
PROJECT_MAX_RETRIES=1
```

If authentication is needed, configure an explicit non-secret label allowlist and a backend-only secret map. Only variable labels are stored with the project; secret values are not returned to the frontend or written to logs:

```env
PROJECT_AUTH_ENV_VARS=RELI_PROJECT_TOKEN_SUPPORT
PROJECT_AUTH_TOKENS_JSON={"RELI_PROJECT_TOKEN_SUPPORT":"replace-with-the-project-token"}
```

The project UI accepts POST/PUT, a JSON request template, an exact-value `{{input_data}}` or `{{input_data.path}}` placeholder, and a JSON response path (for example `result.answer`, `$` for the whole JSON response, or `text` for plain text). Credentials use the configured auth header and scheme. Target status code and duration are recorded on the execution trace; token counts stay unavailable unless a project response integration supplies them (the generic HTTP adapter does not infer token use).

Local Python applications may be connected using trusted, server-installed adapters implementing the existing `Provider` protocol from `app.providers.base`: expose `name`, `model_name`, and `generate(input_data, expected_json) -> GenerationResult`, then register the instance in `app.providers.PROVIDERS`. Start its evaluation through the existing `POST /runs` endpoint using that registered provider name. Adapter code must be installed and reviewed by the operator; ReliAI never executes uploaded Python files. This interface reuses the normal evaluation pipeline and metrics.

## Traces, comparisons, and regressions

Every case execution creates a persisted trace. Fetch traces with `GET /runs/{run_id}/traces` or an individual trace with `GET /runs/{run_id}/traces/{trace_id}`. Trace duration uses a monotonic clock; token counts stay `null` unless the provider supplies them. Execution errors are categorized and sanitized in the trace. A quality score of zero (for example, invalid JSON) remains a completed execution rather than an infrastructure failure.

## Cross-provider benchmarks

Create matched provider runs with `POST /benchmarks`; retrieve persisted history from `GET /benchmarks`, a saved result from `GET /benchmarks/{benchmark_id}`, and the latest grouped provider aggregates from `GET /benchmarks/summary`. Quality values are the arithmetic mean of available case measurements for that metric, and each metric's sample count is the number of cases that supplied it. Failed cases do not contribute quality samples. Case success rates include completed and failed attempts; latency aggregates all measured execution traces, including failed attempts. Token averages include only traces where the provider supplied the corresponding token count. P95 latency is reported only when at least 20 traces are available; smaller samples are shown as unavailable rather than estimated.

Compare runs with `POST /runs/compare`:

```json
{
  "previous_run_id": "UUID",
  "current_run_id": "UUID",
  "thresholds": {
    "exact_match": 0.05,
    "structured_output_valid": 0.05,
    "reference_keyword_coverage": 0.05,
    "latency_ms": 100
  }
}
```

Only runs from the same dataset with matching case identities and metric definitions are compared. The response includes signed and absolute metric differences, per-case status/score/output changes, and newly failed or recovered cases. Missing values are marked unavailable and do not produce regressions. Higher-is-better quality metrics and lower-is-better latency use configurable drop thresholds. The same regression findings are available at `POST /runs/{run_id}/regressions`, with `baseline_run_id` and optional `thresholds` in the request body.

## Local backend development

Use Python 3.12 or newer. From the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:DATABASE_URL = "postgresql+psycopg://reli:reli_local_only@localhost:5432/reli"
alembic upgrade head
uvicorn app.main:app --reload
```

Start the PostgreSQL service with Compose first if it is not already running. For direct backend development, create `backend/.env` from the root `.env.example` and change the database hostname from `db` to `localhost`; settings load `.env` from the backend working directory.

## Tests

Tests use an isolated SQLite database and simulate database failures. They do not require a running PostgreSQL server or any LLM credentials.

```powershell
cd backend
python -m pip install -r requirements.txt
python -m pytest
```

## Frontend development

Use Node.js 20.19+ or 22.12+. From the repository root:

```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```

The Vite server runs at `http://localhost:5173` and connects to `VITE_API_BASE_URL` (default `http://localhost:8002`). The API allows the local Vite origins through its explicit CORS origin list. To create and preview the production SPA bundle:

```powershell
npm run build
npm run preview
```

Docker Compose serves the production frontend via Nginx with SPA route fallback.
