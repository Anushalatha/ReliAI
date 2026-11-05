import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, ChevronLeft, ChevronRight, Play, Search, Zap } from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { datasetsApi } from "../api/datasets";
import { errorMessage } from "../api/client";
import { runsApi } from "../api/runs";
import { tracesApi } from "../api/traces";
import type { EvaluationRun } from "../api/types";
import { usePolling } from "../hooks/usePolling";
import { Button, CopyButton, DataTable, EmptyState, ErrorState, formatDate, Loading, Modal, PageHeading, Panel, StatusBadge, metricDisplay, shortId, notify } from "../components/ui";

function StartRunModal({ onClose, onStarted, initialDatasetId = "" }: { onClose: () => void; onStarted: (run: EvaluationRun) => void; initialDatasetId?: string }) {
  const query = usePolling((signal) => datasetsApi.list(0, 100, signal));
  const [datasetId, setDatasetId] = useState(initialDatasetId);
  const [provider, setProvider] = useState<"mock" | "groq">("mock");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const start = async (event: FormEvent) => {
    event.preventDefault();
    if (!datasetId) return;
    setBusy(true);
    setError("");
    try {
      const run = await runsApi.start(datasetId, provider);
      notify(
        run.status === "completed"
          ? `Evaluation completed with ${run.provider} (${run.model_name})`
          : `Evaluation run finished with status: ${run.status}`,
        run.status === "completed" ? "success" : "error",
      );
      onStarted(run);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  };
  return <Modal title="Start evaluation" description="Mock is the default. Groq is recommended for real inference; credentials remain on the backend." onClose={onClose}>
    <form className="form-stack" onSubmit={start}>
      <label className="field"><span>Dataset <b>*</b></span><select required value={datasetId} onChange={(event) => setDatasetId(event.target.value)}><option value="">Select a dataset…</option>{query.data?.map((dataset) => <option value={dataset.id} key={dataset.id}>{dataset.name} · {dataset.case_count} cases</option>)}</select></label>
      <label className="field"><span>Provider</span><select value={provider} onChange={(event) => setProvider(event.target.value as "mock" | "groq")}><option value="mock">Mock · deterministic, no API key</option><option value="groq">Groq · recommended for real inference</option></select></label>
      <div className="info-box"><Zap size={16} /><span>{provider === "mock" ? <>Mock is deterministic and requires no API key.</> : <>Groq uses the backend-configured model and API key. Requests fail visibly if Groq is unavailable; they never fall back to Mock.</>}</span></div>
      {query.loading && !query.data && <Loading label="Loading saved datasets" />}
      {Boolean(query.error) && <div className="form-errors" role="alert">{errorMessage(query.error)}</div>}
      {query.data?.length === 0 && <div className="info-box">Create a dataset before starting an evaluation.</div>}
      {error && <div className="form-errors" role="alert">{error}</div>}
      <div className="modal-actions"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button disabled={busy || !datasetId || !query.data?.length}>{busy ? "Executing cases…" : "Run evaluation"} <Play size={14} /></Button></div>
    </form>
  </Modal>;
}

export default function Runs() {
  const query = usePolling((signal) => runsApi.list(0, 100, signal), 15_000);
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState("all");
  const [launching, setLaunching] = useState(false);
  const page = Number(params.get("page") ?? 0);
  const search = params.get("q") ?? "";
  const datasets = usePolling((signal) => datasetsApi.list(0, 100, signal), 0);
  const datasetName = useMemo(() => new Map((datasets.data ?? []).map((dataset) => [dataset.id, dataset.name])), [datasets.data]);
  const filtered = (query.data ?? []).filter((run) => {
    const matchesStatus = statusFilter === "all" || run.status === statusFilter;
    const matchesSearch = `${run.id} ${run.name} ${run.provider ?? ""} ${datasetName.get(run.dataset_id ?? "") ?? ""}`.toLowerCase().includes(search.toLowerCase());
    return matchesStatus && matchesSearch;
  });
  const pageSize = 12;
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const rows = filtered.slice(page * pageSize, (page + 1) * pageSize);
  const setSearch = (value: string) => setParams((current) => { if (value) current.set("q", value); else current.delete("q"); current.delete("page"); return current; });

  return <div className="page-stack">
    <PageHeading eyebrow="EVALUATION / RUN HISTORY" title="Evaluation runs" description="Review persisted executions, measured metrics, and case-level outcomes." action={<Button onClick={() => setLaunching(true)}><Play size={15} /> Start evaluation</Button>} />
    <Panel className="table-panel">
      <div className="table-toolbar runs-toolbar">
        <label className="search-field"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search runs, datasets, IDs…" /></label>
        <select className="compact-select" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setParams((current) => { current.delete("page"); return current; }); }} aria-label="Filter by status"><option value="all">All statuses</option><option value="completed">Completed</option><option value="failed">Failed</option><option value="running">Running</option><option value="pending">Pending</option></select>
        <span className="table-count">{filtered.length} runs</span>
      </div>
      {Boolean(query.error && query.data) && <div className="inline-warning">Run history refresh failed. Showing the last successfully loaded data.</div>}
      {Boolean(datasets.error) && <div className="inline-warning">Dataset names could not be refreshed; identifiers may be shown instead.</div>}
      {query.loading && !query.data ? <Loading label="Loading persisted runs" /> : query.error && !query.data ? <ErrorState message={errorMessage(query.error)} retry={query.refresh} /> : rows.length === 0 ? <EmptyState title={search || statusFilter !== "all" ? "No matching runs" : "No evaluation runs yet"} description={search || statusFilter !== "all" ? "Adjust your search or status filter." : "Choose a saved dataset and run it using the deterministic mock provider."} action={statusFilter === "all" && !search && <Button onClick={() => setLaunching(true)}><Play size={15} /> Start evaluation</Button>} /> : <DataTable><thead><tr><th>Evaluation</th><th>Status</th><th>Dataset</th><th>Provider / model</th><th>Exact match</th><th>Created</th><th /></tr></thead><tbody>{rows.map((run) => <tr key={run.id}><td><Link className="table-primary run-primary" to={`/runs/${run.id}`}><span><strong>{run.name}</strong><small>{shortId(run.id, 12)}</small></span></Link><span className="table-id-copy"><CopyButton value={run.id} /></span></td><td><StatusBadge status={run.status} /></td><td>{run.dataset_id ? datasetName.get(run.dataset_id) ?? shortId(run.dataset_id) : "—"}</td><td><span className="provider-cell"><strong>{run.provider ?? "—"}</strong><small>{run.model_name ?? "Model unavailable"}</small></span></td><td>{run.metrics?.exact_match?.value === null || run.metrics?.exact_match?.value === undefined ? <span className="unavailable">Unavailable</span> : <strong className="metric-value">{metricDisplay(run.metrics.exact_match.value, true)}</strong>}</td><td>{formatDate(run.created_at)}</td><td><Link className="icon-link" to={`/runs/${run.id}`} aria-label="Open run"><ArrowRight size={16} /></Link></td></tr>)}</tbody></DataTable>}
      {filtered.length > pageSize && <div className="pagination"><span>Page {page + 1} of {pageCount}</span><div><Button variant="secondary" disabled={page === 0} onClick={() => setParams((current) => { current.set("page", String(page - 1)); return current; })}><ChevronLeft size={15} /> Previous</Button><Button variant="secondary" disabled={page >= pageCount - 1} onClick={() => setParams((current) => { current.set("page", String(page + 1)); return current; })}>Next <ChevronRight size={15} /></Button></div></div>}
    </Panel>
    {launching && <StartRunModal initialDatasetId={params.get("dataset") ?? ""} onClose={() => setLaunching(false)} onStarted={(run) => { setLaunching(false); void query.refresh(); navigate(`/runs/${run.id}`); }} />}
  </div>;
}

export function RunDetails() {
  const { runId = "" } = useParams();
  return <RunDetailContent key={runId} runId={runId} />;
}

function RunDetailContent({ runId: id }: { runId: string }) {
  const query = usePolling((signal) => runsApi.get(id, signal));
  const tracesQuery = usePolling((signal) => tracesApi.listForRun(id, signal));
  const progressQuery = usePolling(
    (signal) => runsApi.progress(id, signal),
    query.data?.status === "running" ? 1_500 : 0,
  );
  useEffect(() => {
    if (
      query.data?.project_id &&
      query.data.status === "running" &&
      (progressQuery.data?.status === "completed" || progressQuery.data?.status === "failed")
    ) {
      void query.refresh();
      void tracesQuery.refresh();
    }
  }, [progressQuery.data?.status, query.data?.project_id, query.data?.status, query.refresh, tracesQuery.refresh]);
  const navigate = useNavigate();
  const run = query.data;
  if (query.loading && !run) return <Loading label="Loading run details" />;
  if (query.error && !run) return <ErrorState message={errorMessage(query.error)} retry={query.refresh} />;
  if (!run) return <ErrorState message="Evaluation run was not found." />;
  const duration = run.started_at && run.completed_at ? Math.max(0, new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()) : null;
  const traces = tracesQuery.data ?? [];
  return <div className="page-stack">
    <button className="back-link" onClick={() => navigate("/runs")}><ArrowLeft size={15} /> All runs</button>
    <PageHeading eyebrow="EVALUATION / RUN DETAIL" title={run.name} description={`Run ${run.id}`} action={<><CopyButton value={run.id} /><Button variant="secondary" onClick={() => navigate(`/compare?current=${run.id}`)}>Compare this run</Button></>} />
    {Boolean(query.error) && <div className="inline-warning">Run refresh failed. Showing the last successfully loaded data.</div>}
    {run.project_id && progressQuery.data && <Panel><div className="panel-heading"><div><h2>Project evaluation progress</h2><p>{progressQuery.data.completed_cases} succeeded · {progressQuery.data.failed_cases} failed · {progressQuery.data.pending_cases} pending of {progressQuery.data.total_cases} cases</p></div><StatusBadge status={progressQuery.data.status} /></div><div style={{ height: 8, overflow: "hidden", borderRadius: 8, background: "var(--line, #292a3c)" }}><div style={{ height: "100%", width: `${progressQuery.data.total_cases ? ((progressQuery.data.completed_cases + progressQuery.data.failed_cases) / progressQuery.data.total_cases) * 100 : 0}%`, background: "var(--violet, #8b5cf6)", transition: "width 200ms ease" }} /></div></Panel>}
    <Panel className="detail-meta"><span><small>STATUS</small><StatusBadge status={run.status} /></span><span><small>DATASET</small><strong>{run.dataset_id ? shortId(run.dataset_id, 12) : "Unavailable"}</strong></span><span><small>PROVIDER</small><strong>{run.provider ?? "Unavailable"}</strong></span><span><small>MODEL</small><strong>{run.model_name ?? "Unavailable"}</strong></span><span><small>DURATION</small><strong>{duration === null ? "Unavailable" : `${duration} ms`}</strong></span><span><small>CREATED</small><strong>{formatDate(run.created_at)}</strong></span></Panel>
    {run.error_message && <div className="failure-banner"><strong>Run execution reported failures</strong><span>{run.error_message}</span></div>}
    <Panel><div className="panel-heading"><div><h2>Aggregate metrics</h2><p>Only reported metrics with available cases are displayed as measured.</p></div></div><div className="aggregate-grid">{Object.entries(run.metrics ?? {}).map(([name, metric]) => <div className="aggregate-metric" key={name}><span>{name.replaceAll("_", " ")}</span><strong>{metric.value === null ? "Unavailable" : metricDisplay(metric.value, true)}</strong><small>{metric.available_cases} / {metric.total_cases} available</small></div>)}</div>{!run.metrics && <EmptyState title="No aggregate metrics" description="The run did not return persisted metric values." />}</Panel>
    <Panel><div className="panel-heading"><div><h2>Case results</h2><p>{run.cases?.length ?? 0} persisted cases · inputs, outputs, and quality signals</p></div></div><div className="case-list">{run.cases?.map((item) => <article className="case-detail" key={item.id}><header><div><span className={`case-status-mark ${item.status}`} /><strong>{item.name}</strong><StatusBadge status={item.status} /></div><div className="case-header-actions"><span className="case-id">case {shortId(item.id)}</span><CopyButton value={item.id} /></div></header>{item.error_message && <div className="trace-error"><strong>Execution error</strong><span>{item.error_message}</span></div>}<div className="code-grid"><div><small>INPUT</small><pre>{JSON.stringify(item.input_data, null, 2)}</pre></div><div><small>EXPECTED OUTPUT</small><pre>{item.expected_output ?? "Not provided"}</pre></div><div><small>ACTUAL OUTPUT</small><pre>{item.actual_output ?? "No output recorded"}</pre></div></div><div className="case-metrics">{Object.entries(item.metrics ?? {}).map(([name, metric]) => <span className="case-metric" key={name}><small>{name.replaceAll("_", " ")}</small><strong>{metric.value === null ? "Unavailable" : metricDisplay(metric.value, true)}</strong></span>)}</div></article>)}</div></Panel>
    <Panel><div className="panel-heading"><div><h2>Execution traces</h2><p>Execution telemetry is distinct from evaluation quality.</p></div><Link className="text-link" to={`/observability?run=${run.id}`}>Open explorer <ArrowRight size={13} /></Link></div>{Boolean(tracesQuery.error && tracesQuery.data) && <div className="inline-warning">Trace refresh failed. Showing the last successfully loaded data.</div>}{tracesQuery.loading && !tracesQuery.data ? <Loading /> : tracesQuery.error && !tracesQuery.data ? <ErrorState message={errorMessage(tracesQuery.error)} retry={tracesQuery.refresh} /> : traces.length ? <DataTable><thead><tr><th>Trace</th><th>Operation</th><th>Status</th><th>Duration</th><th>Provider / model</th><th>Error category</th></tr></thead><tbody>{traces.map((trace) => <tr key={trace.id}><td><code>{shortId(trace.id)}</code></td><td>{trace.operation_name}</td><td><StatusBadge status={trace.status} /></td><td>{trace.latency_ms === null ? "Unavailable" : `${trace.latency_ms} ms`}</td><td>{trace.provider ?? "—"} / {trace.model_name ?? "—"}</td><td>{trace.error_type ?? "—"}</td></tr>)}</tbody></DataTable> : <EmptyState title="No trace records" description="The API has not returned execution traces for this run." />}</Panel>
  </div>;
}
