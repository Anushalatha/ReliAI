import { useMemo } from "react";
import { Activity, CircleCheck, CircleX, Database, Gauge, Play, Timer, Zap } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Link } from "react-router-dom";
import { benchmarksApi } from "../api/benchmarks";
import { errorMessage } from "../api/client";
import { datasetsApi } from "../api/datasets";
import { healthApi } from "../api/health";
import { runsApi } from "../api/runs";
import { tracesApi } from "../api/traces";
import type { EvaluationRun, Trace } from "../api/types";
import { usePolling } from "../hooks/usePolling";
import {
  EmptyState,
  ErrorState,
  formatDate,
  Loading,
  MetricCard,
  Panel,
  PageHeading,
  StatusBadge,
  shortId,
} from "../components/ui";

const colors: Record<string, string> = {
  completed: "#46d39a",
  failed: "#f16d79",
  running: "#e7b65e",
  pending: "#8290a8",
};

interface OverviewData {
  runs: EvaluationRun[];
  benchmarks: Awaited<ReturnType<typeof benchmarksApi.summary>>;
  datasetCount: number;
  traces: Trace[];
  health: string;
  ready: boolean;
}

async function loadOverview(signal: AbortSignal): Promise<OverviewData> {
  const [runs, datasets, live, benchmarks] = await Promise.all([
    runsApi.list(0, 100, signal),
    datasetsApi.list(0, 100, signal),
    healthApi.live(signal),
    benchmarksApi.summary(30, signal),
  ]);
  const traces = await Promise.all(
    runs.slice(0, 12).map((run) => tracesApi.listForRun(run.id, signal)),
  );
  let ready = false;
  try {
    await healthApi.ready(signal);
    ready = true;
  } catch {
    ready = false;
  }
  return {
    runs,
    datasetCount: datasets.length,
    traces: traces.flat(),
    health: live.status,
    ready,
    benchmarks,
  };
}

export default function Overview() {
  const query = usePolling(loadOverview, 20_000);
  const data = query.data;
  const completed = data?.runs.filter((run) => run.status === "completed").length ?? 0;
  const failed = data?.runs.filter((run) => run.status === "failed").length ?? 0;
  const running = data?.runs.filter((run) => run.status === "running" || run.status === "pending").length ?? 0;
  const measuredScores = (data?.runs ?? [])
    .flatMap((run) => {
      const metric = run.metrics?.exact_match;
      return metric?.value !== null && metric?.value !== undefined && metric.available_cases > 0
        ? [{ value: metric.value, samples: metric.available_cases }]
        : [];
    });
  const qualitySampleCount = measuredScores.reduce((total, item) => total + item.samples, 0);
  const avgScore = qualitySampleCount
    ? `${((measuredScores.reduce((sum, item) => sum + item.value * item.samples, 0) / qualitySampleCount) * 100).toFixed(1)}%`
    : "—";
  const measuredLatency = data?.traces.filter(
    (trace): trace is Trace & { latency_ms: number } => trace.latency_ms !== null,
  ) ?? [];
  const averageLatency = measuredLatency.length
    ? `${Math.round(measuredLatency.reduce((sum, trace) => sum + trace.latency_ms, 0) / measuredLatency.length)} ms`
    : "—";
  const statusData = useMemo(() => {
    const counts = new Map<string, number>();
    data?.runs.forEach((run) => counts.set(run.status, (counts.get(run.status) ?? 0) + 1));
    return [...counts].map(([name, value]) => ({ name, value, color: colors[name] ?? "#8290a8" }));
  }, [data?.runs]);
  const activityRuns = data?.runs.slice(0, 6) ?? [];
  const qualityData = (data?.runs ?? [])
    .flatMap((run) => {
      const metric = run.metrics?.exact_match;
      return metric?.value !== null && metric?.value !== undefined && metric.available_cases > 0
        ? [{
          timestamp: new Date(run.created_at).getTime(),
          label: new Date(run.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
          score: metric.value * 100,
          samples: metric.available_cases,
        }]
        : [];
    })
    .sort((left, right) => left.timestamp - right.timestamp)
    .slice(-14);

  if (query.loading && !data) return <Loading label="Loading persisted platform data" />;
  if (query.error && !data) return <ErrorState message={errorMessage(query.error)} retry={query.refresh} />;

  return (
    <div className="page-stack">
      <PageHeading
        eyebrow="OPERATIONS / OVERVIEW"
        title="System overview"
        description="A live view of persisted evaluations and measured execution data."
        action={<Link className="button button-primary" to="/runs"><Play size={15} /> New evaluation</Link>}
      />
      {data && (
        <div className="system-strip">
          <div className="system-status"><span className={`pulse-dot ${data.ready ? "healthy" : "unhealthy"}`} /><div><strong>{data.ready ? "All systems operational" : "Database readiness unavailable"}</strong><small>Backend {data.health} · Database {data.ready ? "connected" : "unavailable"}</small></div></div>
          <div className="system-update"><span>{query.refreshing ? "Refreshing…" : "Last successful refresh"}</span><strong>{query.updatedAt?.toLocaleTimeString() ?? "—"}</strong></div>
        </div>
      )}
      {Boolean(query.error && data) && <div className="inline-warning">Refresh failed. Showing the last successfully loaded data.</div>}

      <div className="metric-grid">
        <MetricCard label="Evaluation runs" value={data?.runs.length ?? "—"} detail="Latest 100 persisted runs" icon={<Activity size={18} />} />
        <MetricCard label="Completed" value={completed} detail={`${running} in progress`} icon={<CircleCheck size={18} />} accent="green" />
        <MetricCard label="Failed runs" value={failed} detail="Execution failures recorded" icon={<CircleX size={18} />} accent="red" />
        <MetricCard label="Exact match avg." value={avgScore} detail={`${qualitySampleCount} cases measured across available runs`} icon={<Gauge size={18} />} accent="cyan" />
        <MetricCard label="Measured latency" value={averageLatency} detail={`${measuredLatency.length} measured traces · latest 12 runs`} icon={<Timer size={18} />} accent="amber" />
        <MetricCard label="Datasets" value={data?.datasetCount ?? "—"} detail="Persisted evaluation datasets" icon={<Database size={18} />} accent="violet" />
      </div>

      <div className="dashboard-grid">
        <Panel className="chart-panel">
          <div className="panel-heading"><div><h2>Quality trend</h2><p>Measured exact match per run · sample count on hover</p></div><span className="chart-legend"><i className="legend-cyan" /> Exact match</span></div>
          {qualityData.length >= 2 ? (
            <div className="chart-area"><ResponsiveContainer width="100%" height="100%"><AreaChart data={qualityData} margin={{ top: 10, right: 12, bottom: 0, left: -18 }}><defs><linearGradient id="scoreFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#52d6e8" stopOpacity={0.22} /><stop offset="100%" stopColor="#52d6e8" stopOpacity={0.01} /></linearGradient></defs><CartesianGrid stroke="#242b3a" strokeDasharray="3 5" vertical={false} /><XAxis dataKey="label" tick={{ fill: "#8791a5", fontSize: 11 }} axisLine={false} tickLine={false} /><YAxis domain={[0, 100]} tick={{ fill: "#8791a5", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(value: number) => `${value}%`} /><Tooltip contentStyle={{ background: "#10141f", border: "1px solid #242b3a", borderRadius: 8 }} labelStyle={{ color: "#dce3f1" }} formatter={(value: number, _name, item) => [`${value.toFixed(1)}% · n=${item.payload.samples}`, "Exact match"]} /><Area type="monotone" dataKey="score" stroke="#52d6e8" strokeWidth={2} fill="url(#scoreFill)" activeDot={{ r: 4, fill: "#52d6e8" }} /></AreaChart></ResponsiveContainer></div>
          ) : <EmptyState title="Not enough metric history" description="At least two persisted runs with measured exact-match cases are needed to draw a meaningful trend." />}
        </Panel>
        <Panel className="chart-panel status-chart-panel">
          <div className="panel-heading"><div><h2>Run distribution</h2><p>By persisted status</p></div></div>
          {statusData.length ? <div className="status-chart-wrap"><ResponsiveContainer width="100%" height={185}><PieChart><Pie data={statusData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={78} paddingAngle={3} stroke="none">{statusData.map((item) => <Cell key={item.name} fill={item.color} />)}</Pie><Tooltip contentStyle={{ background: "#10141f", border: "1px solid #242b3a", borderRadius: 8 }} /></PieChart></ResponsiveContainer><div className="status-legend">{statusData.map((item) => <div key={item.name}><i style={{ background: item.color }} /><span>{item.name}</span><strong>{item.value}</strong></div>)}</div></div> : <EmptyState title="No runs recorded" description="Start an evaluation to see run status distribution." action={<Link to="/runs" className="text-link">View evaluation runs</Link>} />}
        </Panel>
      </div>

      <Panel className="table-panel benchmark-dashboard">
        <div className="panel-heading">
          <div><h2>Provider performance comparison</h2><p>Aggregated from the latest 30 persisted benchmark groups; measurements include explicit sample counts.</p></div>
          <Link to="/benchmarks" className="text-link">Benchmark history <Zap size={13} /></Link>
        </div>
        {data?.benchmarks.provider_results.length ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Provider / model</th><th>Exact match</th><th>JSON validity</th><th>Keyword coverage</th><th>Avg / median latency</th><th>P95 latency</th><th>Avg tokens in / out</th><th>Case outcomes</th><th>Run outcomes</th><th>Errors</th></tr></thead>
              <tbody>{data.benchmarks.provider_results.map((provider) => {
                const exact = provider.quality_metrics.exact_match;
                const structured = provider.quality_metrics.structured_output_valid;
                const keywords = provider.quality_metrics.reference_keyword_coverage;
                const qualityCell = (value: number | null, samples: number) => value === null
                  ? <span className="unavailable">Unavailable · n={samples}</span>
                  : <>{(value * 100).toFixed(1)}% · n={samples}</>;
                const latency = provider.latency;
                const tokensIn = provider.input_tokens;
                const tokensOut = provider.output_tokens;
                const attempts = provider.case_outcomes.attempts;
                const failureKinds = Object.entries(provider.error_counts).filter(([, count]) => count > 0);
                return <tr key={provider.provider}>
                  <td><span className="provider-cell"><strong>{provider.provider === "mock" ? "Mock · simulated" : provider.provider}</strong><small>{provider.models.join(", ") || "Model unavailable"}</small></span></td>
                  <td>{qualityCell(exact.value, exact.sample_count)}</td>
                  <td>{qualityCell(structured.value, structured.sample_count)}</td>
                  <td>{qualityCell(keywords.value, keywords.sample_count)}</td>
                  <td>{latency.average_ms === null ? "Unavailable" : `${latency.average_ms.toFixed(1)} / ${latency.median_ms?.toFixed(1)} ms` } · n={latency.sample_count}</td>
                  <td>{latency.p95_ms === null ? `Unavailable · ${latency.sample_count}/${latency.p95_minimum_samples}` : `${latency.p95_ms.toFixed(1)} ms`} · n={latency.sample_count}</td>
                  <td>{tokensIn.average_tokens === null ? "Unavailable" : `${tokensIn.average_tokens.toFixed(1)}`} / {tokensOut.average_tokens === null ? "Unavailable" : `${tokensOut.average_tokens.toFixed(1)}`} · n={tokensIn.sample_count}/{tokensOut.sample_count}</td>
                  <td>{attempts ? `${provider.case_outcomes.successes} pass · ${provider.case_outcomes.failures} fail` : "Unavailable"} · n={attempts}</td>
                  <td>{provider.run_outcomes.completed} completed · {provider.run_outcomes.failed} failed · n={provider.run_outcomes.sample_count}</td>
                  <td>{failureKinds.length ? failureKinds.map(([category, count]) => `${category.replaceAll("_", " ")} ${count}`).join(", ") : "None recorded"}</td>
                </tr>;
              })}</tbody>
            </table>
          </div>
        ) : <EmptyState title="No benchmark measurements yet" description="Create a persisted benchmark to compare provider quality, latency, token usage, and failures." action={<Link to="/benchmarks" className="text-link">Start a benchmark <Zap size={13} /></Link>} />}
        <div className="benchmark-history-preview">
          <strong>Recent benchmark runs</strong>
          {data?.benchmarks.recent_benchmarks.length ? data.benchmarks.recent_benchmarks.slice(0, 5).map((benchmark) => (
            <Link to={`/benchmarks/${benchmark.id}`} key={benchmark.id} className="activity-row">
              <span className={`activity-icon ${benchmark.status === "completed" ? "completed" : benchmark.status === "failed" ? "failed" : ""}`}><Activity size={15} /></span>
              <span className="activity-main"><strong>{benchmark.name}</strong><small>{benchmark.providers.map((provider) => provider === "mock" ? "Mock (simulated)" : provider).join(" · ")} · {formatDate(benchmark.created_at)}</small></span>
              <StatusBadge status={benchmark.status} />
            </Link>
          )) : <span className="unavailable">No benchmark history available.</span>}
        </div>
      </Panel>

      <div className="bottom-grid">
        <Panel className="activity-panel">
          <div className="panel-heading"><div><h2>Recent evaluations</h2><p>Activity derived from persisted run records</p></div><Link to="/runs" className="text-link">All runs <Zap size={13} /></Link></div>
          {activityRuns.length ? <div className="activity-list">{activityRuns.map((run) => <Link className="activity-row" to={`/runs/${run.id}`} key={run.id}><span className={`activity-icon ${run.status}`}><Activity size={15} /></span><span className="activity-main"><strong>{run.name}</strong><small>{shortId(run.id)} · {formatDate(run.created_at)}</small></span><StatusBadge status={run.status} /></Link>)}</div> : <EmptyState title="Nothing to show yet" description="Run activity will appear here after the first evaluation." />}</Panel>
        <Panel className="quick-panel">
          <div className="panel-heading"><div><h2>Quick actions</h2><p>Continue your evaluation workflow</p></div></div>
          <Link className="quick-action" to="/datasets"><span className="quick-icon"><Database size={17} /></span><span><strong>Create a dataset</strong><small>Define prompts and expected behavior</small></span><span className="quick-arrow">↗</span></Link>
          <Link className="quick-action" to="/runs"><span className="quick-icon cyan"><Zap size={17} /></span><span><strong>Start an evaluation</strong><small>Execute cases with deterministic mock</small></span><span className="quick-arrow">↗</span></Link>
          <Link className="quick-action" to="/compare"><span className="quick-icon green"><Activity size={17} /></span><span><strong>Compare runs</strong><small>Inspect quality and case-level changes</small></span><span className="quick-arrow">↗</span></Link>
        </Panel>
      </div>
    </div>
  );
}
