import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, ChevronLeft, ChevronRight, Search, X } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { errorMessage } from "../api/client";
import { runsApi } from "../api/runs";
import { tracesApi } from "../api/traces";
import type { Trace } from "../api/types";
import { usePolling } from "../hooks/usePolling";
import { Button, CopyButton, DataTable, EmptyState, ErrorState, formatDate, Loading, PageHeading, Panel, StatusBadge, shortId } from "../components/ui";

interface TraceFeed {
  traces: Trace[];
  runNames: Map<string, string>;
}

async function loadTraceFeed(signal: AbortSignal): Promise<TraceFeed> {
  const runs = await runsApi.list(0, 30, signal);
  const entries = await Promise.all(runs.map(async (run) => ({
    run,
    traces: await tracesApi.listForRun(run.id, signal),
  })));
  return {
    traces: entries.flatMap(({ traces }) => traces).sort((a, b) => b.started_at.localeCompare(a.started_at)),
    runNames: new Map(entries.map(({ run }) => [run.id, run.name])),
  };
}

function TraceDrawer({ trace, onClose }: { trace: Trace; onClose: () => void }) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);
  return <div className="drawer-backdrop" role="presentation" onMouseDown={(event) => {
    if (event.target === event.currentTarget) onClose();
  }}>
    <aside className="trace-drawer" role="dialog" aria-modal="true" aria-labelledby="trace-title">
      <header><div><div className="eyebrow">EXECUTION / TRACE</div><h2 id="trace-title">Trace details</h2></div><button className="icon-button" onClick={onClose} aria-label="Close trace details"><X size={18} /></button></header>
      <div className="drawer-scroll">
        <div className="drawer-status"><StatusBadge status={trace.status} /><span>{trace.operation_name}</span></div>
        <div className="detail-list">
          <div><small>TRACE ID</small><span><code>{trace.id}</code><CopyButton value={trace.id} /></span></div>
          <div><small>RUN ID</small><span><Link to={`/runs/${trace.run_id}`} onClick={onClose}><code>{shortId(trace.run_id, 14)}</code><ArrowUpRight size={13} /></Link><CopyButton value={trace.run_id} /></span></div>
          <div><small>CASE ID</small><span>{trace.case_id ? <><code>{trace.case_id}</code><CopyButton value={trace.case_id} /></> : "Unavailable"}</span></div>
          <div><small>REQUEST ID</small><span>{trace.request_id ?? "Unavailable"}{trace.request_id && <CopyButton value={trace.request_id} />}</span></div>
          <div><small>STARTED</small><strong>{formatDate(trace.started_at)}</strong></div>
          <div><small>COMPLETED</small><strong>{formatDate(trace.completed_at)}</strong></div>
          <div><small>DURATION</small><strong>{trace.latency_ms === null ? "Unavailable" : `${trace.latency_ms} ms`}</strong></div>
          <div><small>PROVIDER</small><strong>{trace.provider ?? "Unavailable"}</strong></div>
          <div><small>MODEL</small><strong>{trace.model_name ?? "Unavailable"}</strong></div>
          <div><small>INPUT TOKENS</small><strong>{trace.input_tokens ?? "Unavailable"}</strong></div>
          <div><small>OUTPUT TOKENS</small><strong>{trace.output_tokens ?? "Unavailable"}</strong></div>
        </div>
        {trace.error_type && <div className="trace-error detail-error"><strong>Execution failure · {trace.error_type.replaceAll("_", " ")}</strong><span>{trace.error_message ?? "No sanitized error message."}</span>{trace.error_details && <pre>{JSON.stringify(trace.error_details, null, 2)}</pre>}</div>}
        {!trace.error_type && <div className="info-box"><span className="quality-note">{trace.status === "succeeded" ? "Execution succeeded." : trace.status === "running" ? "Execution is in progress." : "Execution status is not classified as an error."} Evaluation quality is measured separately in the associated case result.</span></div>}
        {trace.trace_metadata && <div className="drawer-json"><small>TRACE METADATA</small><pre>{JSON.stringify(trace.trace_metadata, null, 2)}</pre></div>}
      </div>
    </aside>
  </div>;
}

export default function Observability() {
  const [params] = useSearchParams();
  const runFilter = params.get("run") ?? "";
  const query = usePolling(loadTraceFeed, 30_000);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [selected, setSelected] = useState<Trace | null>(null);
  const [page, setPage] = useState(0);
  const filtered = useMemo(() => (query.data?.traces ?? []).filter((trace) => {
    const text = `${trace.id} ${trace.run_id} ${trace.case_id ?? ""} ${trace.operation_name} ${trace.provider ?? ""} ${trace.model_name ?? ""} ${trace.error_type ?? ""} ${trace.request_id ?? ""}`.toLowerCase();
    return (!runFilter || trace.run_id === runFilter) && (status === "all" || trace.status === status) && text.includes(search.toLowerCase());
  }), [query.data, search, status, runFilter]);
  const pageSize = 12;
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const rows = filtered.slice(page * pageSize, (page + 1) * pageSize);

  return <div className="page-stack">
    <PageHeading eyebrow="OBSERVABILITY / TRACE EXPLORER" title="Execution observability" description="Inspect persisted provider executions, timings, and sanitized failures." />
    <div className="observability-callout"><span className="telemetry-symbol">⌁</span><div><strong>Execution and quality are separate signals</strong><small>Trace status reflects provider execution. Quality metrics belong to each evaluation case and are never inferred from trace health.</small></div><span className="polling-label"><i /> Polling every 30s</span></div>
    <Panel className="table-panel">
      <div className="table-toolbar"><label className="search-field"><Search size={16} /><input value={search} onChange={(event) => { setSearch(event.target.value); setPage(0); }} placeholder="Search trace, run, provider, errors…" /></label><select className="compact-select" value={status} onChange={(event) => { setStatus(event.target.value); setPage(0); }} aria-label="Filter trace status"><option value="all">All statuses</option><option value="succeeded">Succeeded</option><option value="failed">Failed</option><option value="running">Running</option></select><span className="table-count">{filtered.length} traces · latest 30 runs</span></div>
      {Boolean(query.error && query.data) && <div className="inline-warning">Trace refresh failed. Showing the last successfully loaded data.</div>}
      {query.loading && !query.data ? <Loading label="Loading persisted traces" /> : query.error && !query.data ? <ErrorState message={errorMessage(query.error)} retry={query.refresh} /> : rows.length ? <DataTable><thead><tr><th>Trace</th><th>Operation</th><th>Status</th><th>Duration</th><th>Provider / model</th><th>Error category</th><th>Started</th><th /></tr></thead><tbody>{rows.map((trace) => <tr key={trace.id} className="clickable-row" onClick={() => setSelected(trace)}><td><span className="id-inline"><code>{shortId(trace.id)}</code><CopyButton value={trace.id} /></span></td><td><strong className="operation-name">{trace.operation_name}</strong><small className="sub-cell">{query.data?.runNames.get(trace.run_id) ?? shortId(trace.run_id)}</small></td><td><StatusBadge status={trace.status} /></td><td>{trace.latency_ms === null ? "Unavailable" : <strong>{trace.latency_ms} ms</strong>}</td><td><span className="provider-cell"><strong>{trace.provider ?? "—"}</strong><small>{trace.model_name ?? "Model unavailable"}</small></span></td><td>{trace.error_type ? <span className="error-category">{trace.error_type.replaceAll("_", " ")}</span> : "—"}</td><td>{formatDate(trace.started_at)}</td><td><button className="icon-link" aria-label="View trace detail" onClick={(event) => { event.stopPropagation(); setSelected(trace); }}><ArrowUpRight size={15} /></button></td></tr>)}</tbody></DataTable> : <EmptyState title={runFilter ? "No traces for this run" : "No trace records yet"} description={runFilter ? "The selected run has no execution traces." : "Create and run an evaluation. Trace records are loaded from the latest persisted runs."} />}
      {filtered.length > pageSize && <div className="pagination"><span>Page {page + 1} of {pages}</span><div><Button variant="secondary" disabled={page === 0} onClick={() => setPage((value) => value - 1)}><ChevronLeft size={15} /> Previous</Button><Button variant="secondary" disabled={page >= pages - 1} onClick={() => setPage((value) => value + 1)}>Next <ChevronRight size={15} /></Button></div></div>}
    </Panel>
    {selected && <TraceDrawer trace={selected} onClose={() => setSelected(null)} />}
  </div>;
}
