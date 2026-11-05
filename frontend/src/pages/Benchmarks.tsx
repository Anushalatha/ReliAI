import { useState, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, Play } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { benchmarksApi, type BenchmarkInput } from "../api/benchmarks";
import { datasetsApi } from "../api/datasets";
import { errorMessage } from "../api/client";
import type { BenchmarkDetail, BenchmarkProviderResult } from "../api/types";
import { usePolling } from "../hooks/usePolling";
import {
  Button,
  EmptyState,
  ErrorState,
  formatDate,
  Loading,
  PageHeading,
  Panel,
  StatusBadge,
  notify,
} from "../components/ui";

function BenchmarkForm({ onCreated }: { onCreated: (benchmark: BenchmarkDetail) => void }) {
  const datasets = usePolling((signal) => datasetsApi.list(0, 100, signal));
  const [datasetId, setDatasetId] = useState("");
  const [name, setName] = useState("");
  const [providers, setProviders] = useState<Array<"mock" | "groq">>(["mock", "groq"]);
  const [groqModel, setGroqModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const canStart = Boolean(datasetId) && providers.length > 0 && !busy;

  const toggleProvider = (provider: "mock" | "groq") => {
    setProviders((selected) => selected.includes(provider)
      ? selected.filter((item) => item !== provider)
      : [...selected, provider]);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!canStart) return;
    setBusy(true);
    setError("");
    try {
      const payload: BenchmarkInput = {
        dataset_id: datasetId,
        providers,
        ...(name.trim() ? { name: name.trim() } : {}),
        ...(groqModel.trim() ? { groq_model: groqModel.trim() } : {}),
      };
      const benchmark = await benchmarksApi.create(payload);
      notify(`Benchmark finished with status: ${benchmark.status}`, benchmark.status === "failed" ? "error" : "success");
      onCreated(benchmark);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel className="benchmark-create">
      <div className="panel-heading"><div><h2>New benchmark</h2><p>Each selected provider runs the same persisted dataset cases independently.</p></div></div>
      <form className="benchmark-form" onSubmit={submit}>
        <label className="field">
          <span>Dataset <b>*</b></span>
          <select required value={datasetId} onChange={(event) => setDatasetId(event.target.value)}>
            <option value="">Select a saved dataset…</option>
            {datasets.data?.map((dataset) => <option value={dataset.id} key={dataset.id}>{dataset.name} · {dataset.case_count} cases</option>)}
          </select>
        </label>
        {datasets.loading && !datasets.data && <Loading label="Loading saved datasets" />}
        {datasets.data?.length === 0 && <div className="info-box">Create a dataset before starting a benchmark.</div>}
        <label className="field">
          <span>Benchmark name <small>Optional</small></span>
          <input value={name} onChange={(event) => setName(event.target.value)} maxLength={200} placeholder="Defaults to the dataset name" />
        </label>
        <fieldset className="benchmark-providers">
          <legend>Providers <b>*</b></legend>
          <label><input type="checkbox" checked={providers.includes("groq")} onChange={() => toggleProvider("groq")} /><span><strong>Groq</strong><small>Real inference · recommended</small></span></label>
          <label><input type="checkbox" checked={providers.includes("mock")} onChange={() => toggleProvider("mock")} /><span><strong>Mock</strong><small>Simulated deterministic baseline · not a real LLM</small></span></label>
        </fieldset>
        {providers.includes("groq") && <label className="field">
          <span>Groq model override <small>Optional</small></span>
          <input value={groqModel} onChange={(event) => setGroqModel(event.target.value)} maxLength={200} placeholder="Use backend GROQ_MODEL setting" />
          <small>Groq credentials remain backend-only. Provider failures are recorded; Mock is never substituted.</small>
        </label>}
        {Boolean(datasets.error) && <div className="form-errors">{errorMessage(datasets.error)}</div>}
        {error && <div className="form-errors" role="alert">{error}</div>}
        <div className="info-box">Results are descriptive measurements, not a statistical significance test. Missing quality, latency, or token measurements remain unavailable.</div>
        <Button disabled={!canStart || providers.length === 0 || !datasets.data?.length}>
          <Play size={15} /> {busy ? "Running providers…" : "Run benchmark"}
        </Button>
      </form>
    </Panel>
  );
}

function displayMetric(value: number | null | undefined, samples?: number) {
  if (value === null || value === undefined) return "Unavailable";
  const formatted = `${(value * 100).toFixed(1)}%`;
  return samples === undefined ? formatted : `${formatted} · n=${samples}`;
}

function ProviderResult({ result }: { result: BenchmarkProviderResult }) {
  const qualityLabels: Record<string, string> = {
    exact_match: "Exact match",
    structured_output_valid: "Structured output validity",
    reference_keyword_coverage: "Reference keyword coverage",
  };
  const runIds = result.run_ids;
  return (
    <section className="benchmark-provider-result">
      <header>
        <div><h3>{result.provider === "mock" ? "Mock (simulated)" : result.provider}</h3><p>{result.models.length ? result.models.join(", ") : "Model unavailable"}</p></div>
        <span className="benchmark-sample">{result.case_outcomes.sample_count} case samples · {result.run_outcomes.sample_count} run samples</span>
      </header>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Measure</th><th>Value</th><th>Samples</th></tr></thead>
          <tbody>
            {Object.entries(qualityLabels).map(([key, label]) => {
              const metric = result.quality_metrics[key];
              return <tr key={key}><td>{label}</td><td>{displayMetric(metric?.value)}</td><td>{metric?.sample_count ?? 0} cases</td></tr>;
            })}
            <tr><td>Average latency</td><td>{result.latency.average_ms === null ? "Unavailable" : `${result.latency.average_ms.toFixed(1)} ms`}</td><td>{result.latency.sample_count} traces</td></tr>
            <tr><td>Median / P50 latency</td><td>{result.latency.median_ms === null ? "Unavailable" : `${result.latency.median_ms.toFixed(1)} ms`}</td><td>{result.latency.sample_count} traces</td></tr>
            <tr><td>P95 latency</td><td>{result.latency.p95_ms === null ? `Unavailable · needs ${result.latency.p95_minimum_samples} samples` : `${result.latency.p95_ms.toFixed(1)} ms`}</td><td>{result.latency.sample_count} traces</td></tr>
            <tr><td>Average input tokens</td><td>{result.input_tokens.average_tokens === null ? "Unavailable" : result.input_tokens.average_tokens.toFixed(1)}</td><td>{result.input_tokens.sample_count} traces</td></tr>
            <tr><td>Average output tokens</td><td>{result.output_tokens.average_tokens === null ? "Unavailable" : result.output_tokens.average_tokens.toFixed(1)}</td><td>{result.output_tokens.sample_count} traces</td></tr>
            <tr><td>Case execution success</td><td>{displayMetric(result.case_outcomes.success_rate, result.case_outcomes.sample_count)}</td><td>{result.case_outcomes.successes} succeeded · {result.case_outcomes.failures} failed</td></tr>
            <tr><td>Run outcomes</td><td>{result.run_outcomes.completed} completed · {result.run_outcomes.failed} failed</td><td>{result.run_outcomes.sample_count} runs</td></tr>
          </tbody>
        </table>
      </div>
      <div className="benchmark-errors"><strong>Execution errors</strong>{Object.entries(result.error_counts).filter(([, count]) => count > 0).length
        ? Object.entries(result.error_counts).filter(([, count]) => count > 0).map(([category, count]) => <span className="mini-chip danger" key={category}>{category.replaceAll("_", " ")} · {count}</span>)
        : <span className="unavailable">No failed execution traces recorded</span>}</div>
      <div className="benchmark-run-links">{runIds.map((id) => <Link className="text-link" to={`/runs/${id}`} key={id}>Inspect persisted run <ArrowRight size={13} /></Link>)}</div>
    </section>
  );
}

function BenchmarkDetailView({ id }: { id: string }) {
  const query = usePolling((signal) => benchmarksApi.get(id, signal));
  if (query.loading && !query.data) return <Loading label="Loading persisted benchmark" />;
  if (query.error && !query.data) return <ErrorState message={errorMessage(query.error)} retry={query.refresh} />;
  const benchmark = query.data;
  if (!benchmark) return <EmptyState title="Benchmark unavailable" description="This benchmark does not exist or is no longer available." />;
  return (
    <div className="page-stack">
      <Link to="/benchmarks" className="text-link"><ArrowLeft size={14} /> All benchmarks</Link>
      <PageHeading eyebrow="BENCHMARK / RESULTS" title={benchmark.name} description={`${benchmark.dataset_name ?? "Dataset unavailable"} · ${benchmark.case_count} cases`} />
      <Panel>
        <div className="detail-meta">
          <span><small>Status</small><StatusBadge status={benchmark.status} /></span>
          <span><small>Dataset</small><strong>{benchmark.dataset_name ?? "Unavailable"}</strong></span>
          <span><small>Providers</small><strong>{benchmark.providers.map((provider) => provider === "mock" ? "Mock (simulated)" : provider).join(" · ")}</strong></span>
          <span><small>Created</small><strong>{formatDate(benchmark.created_at)}</strong></span>
          <span><small>Benchmark ID</small><strong className="mono">{benchmark.id}</strong></span>
        </div>
        {benchmark.status === "partial" && <div className="inline-warning benchmark-warning">Some provider runs failed. Successful provider data is retained and failures are shown below.</div>}
        {benchmark.results.length ? benchmark.results.map((result) => <ProviderResult result={result} key={result.provider} />) : <EmptyState title="No provider results persisted" description="No provider run was successfully associated with this benchmark." />}
        <p className="benchmark-footnote">All counts describe persisted cases, traces, or runs. These are descriptive results only; no significance testing or inference cost estimate is included.</p>
      </Panel>
    </div>
  );
}

export default function Benchmarks() {
  const { benchmarkId } = useParams();
  const navigate = useNavigate();
  const history = usePolling((signal) => benchmarksApi.list(0, 100, signal), 20_000);
  if (benchmarkId) return <BenchmarkDetailView key={benchmarkId} id={benchmarkId} />;
  return (
    <div className="page-stack">
      <PageHeading eyebrow="EVALUATION / CROSS-PROVIDER" title="Benchmarks" description="Run matched persisted cases across Groq and the simulated Mock provider, then inspect measured outcomes." />
      <BenchmarkForm onCreated={(benchmark) => navigate(`/benchmarks/${benchmark.id}`)} />
      <Panel className="table-panel">
        <div className="panel-heading"><div><h2>Benchmark history</h2><p>Persisted benchmark groups and their provider runs</p></div><span className="table-count">{history.data?.length ?? 0} groups</span></div>
        {history.loading && !history.data ? <Loading label="Loading benchmark history" />
          : history.error && !history.data ? <ErrorState message={errorMessage(history.error)} retry={history.refresh} />
            : history.data?.length ? <div className="table-wrap"><table><thead><tr><th>Benchmark</th><th>Status</th><th>Providers</th><th>Created</th><th /></tr></thead><tbody>
              {history.data.map((benchmark) => <tr key={benchmark.id}><td><Link className="table-primary" to={`/benchmarks/${benchmark.id}`}><strong>{benchmark.name}</strong></Link></td><td><StatusBadge status={benchmark.status} /></td><td>{benchmark.providers.map((provider) => provider === "mock" ? "Mock (simulated)" : provider).join(" · ")}</td><td>{formatDate(benchmark.created_at)}</td><td><Link className="icon-link" to={`/benchmarks/${benchmark.id}`} aria-label="Open benchmark"><ArrowRight size={16} /></Link></td></tr>)}
            </tbody></table></div>
            : <EmptyState title="No benchmarks yet" description="Choose a saved dataset and providers above to create a persisted cross-provider benchmark." />}
        {Boolean(history.error && history.data) && <div className="inline-warning">Benchmark history refresh failed. Showing the last successfully loaded data.</div>}
      </Panel>
    </div>
  );
}
