import { useMemo, useState } from "react";
import { ArrowDown, ArrowRight, ArrowUp, Check, GitCompareArrows, ShieldAlert, X } from "lucide-react";
import { useSearchParams, Link } from "react-router-dom";
import { errorMessage } from "../api/client";
import { runsApi } from "../api/runs";
import type { EvaluationRun, RunComparison as RunComparisonType } from "../api/types";
import { usePolling } from "../hooks/usePolling";
import { Button, DataTable, EmptyState, ErrorState, Loading, PageHeading, Panel, StatusBadge, formatDate, metricDisplay, shortId } from "../components/ui";

const initialThresholds = {
  exact_match: 0.05,
  structured_output_valid: 0.05,
  reference_keyword_coverage: 0.05,
  latency_ms: 100,
};

const metricLabels: Record<string, string> = {
  exact_match: "Exact match",
  structured_output_valid: "Structured output validity",
  reference_keyword_coverage: "Keyword coverage",
  latency_ms: "Latency",
};

function metricValue(value: number | null, metric: string) {
  if (value === null) return "Unavailable";
  return metric === "latency_ms" ? `${value.toFixed(1)} ms` : metricDisplay(value, true);
}

function RunSelect({ label, value, onChange, runs, exclude }: { label: string; value: string; onChange: (value: string) => void; runs: EvaluationRun[]; exclude?: string }) {
  return <label className="field"><span>{label} <b>*</b></span><select required value={value} onChange={(event) => onChange(event.target.value)}><option value="">Select a persisted run…</option>{runs.filter((run) => run.id !== exclude).map((run) => <option value={run.id} key={run.id}>{run.name} · {run.status} · {formatDate(run.created_at)} · {shortId(run.id)}</option>)}</select></label>;
}

export default function Comparison({ regressionMode = false }: { regressionMode?: boolean }) {
  const [params] = useSearchParams();
  const runsQuery = usePolling((signal) => runsApi.list(0, 100, signal), 15_000);
  const runs = runsQuery.data ?? [];
  const [previousId, setPreviousId] = useState(params.get(regressionMode ? "baseline" : "previous") ?? "");
  const [currentId, setCurrentId] = useState(params.get(regressionMode ? "current" : "current") ?? "");
  const [thresholds, setThresholds] = useState(initialThresholds);
  const [result, setResult] = useState<RunComparisonType | null>(null);
  const [beforeRun, setBeforeRun] = useState<EvaluationRun | null>(null);
  const [afterRun, setAfterRun] = useState<EvaluationRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const runCompare = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const comparison = regressionMode
        ? await runsApi.regressions(currentId, previousId, thresholds)
        : await runsApi.compare(previousId, currentId, thresholds);
      setResult(comparison);
      if (comparison.status === "compatible") {
        const [before, after] = await Promise.all([runsApi.get(previousId), runsApi.get(currentId)]);
        setBeforeRun(before);
        setAfterRun(after);
      }
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  };
  const caseOutputs = useMemo(() => {
    const before = new Map((beforeRun?.cases ?? []).map((item) => [item.dataset_case_id ?? item.id, item.actual_output]));
    const after = new Map((afterRun?.cases ?? []).map((item) => [item.dataset_case_id ?? item.id, item.actual_output]));
    return { before, after };
  }, [beforeRun, afterRun]);
  const availableCount = result?.metrics.filter((metric) => metric.available).length ?? 0;
  const findings = result?.regressions ?? [];

  return <div className="page-stack">
    <PageHeading eyebrow={regressionMode ? "RELIABILITY / REGRESSION MONITOR" : "EVALUATION / RUN COMPARISON"} title={regressionMode ? "Regression monitor" : "Run comparison"} description={regressionMode ? "Check a current evaluation against a persisted baseline using explicit thresholds." : "Compare compatible evaluations without treating missing measurements as zero."} />
    <Panel className="compare-form-panel">
      <div className="panel-heading"><div><h2>{regressionMode ? "Configure regression check" : "Select evaluations"}</h2><p>Only persisted runs are available. Incompatible inputs or metric definitions are rejected by the backend.</p></div></div>
      {Boolean(runsQuery.error && runsQuery.data) && <div className="inline-warning">Run history refresh failed. Showing the last successfully loaded data.</div>}
      {runsQuery.loading && !runsQuery.data ? <Loading label="Loading run history" /> : runsQuery.error && !runsQuery.data ? <ErrorState message={errorMessage(runsQuery.error)} retry={runsQuery.refresh} /> : !runs.length ? <EmptyState title="No runs available to compare" description="Create persisted evaluation runs before comparing results." action={<Link className="text-link" to="/runs">View evaluation runs</Link>} /> : <form onSubmit={runCompare} className="compare-form">
        <div className="form-grid"><RunSelect label="Baseline / previous run" value={previousId} onChange={setPreviousId} runs={runs} exclude={currentId} /><RunSelect label="Current run" value={currentId} onChange={setCurrentId} runs={runs} exclude={previousId} /></div>
        <div className="threshold-heading"><div><strong>Regression thresholds</strong><small>These defaults mirror the backend API. Adjust to the change that should trigger a finding.</small></div></div>
        <div className="threshold-grid">{Object.entries(thresholds).map(([metric, value]) => <label className="field threshold-field" key={metric}><span>{metricLabels[metric]}</span><div className="number-suffix"><input type="number" step={metric === "latency_ms" ? "1" : "0.01"} min="0" max={metric === "latency_ms" ? undefined : "1"} value={value} onChange={(event) => setThresholds((previous) => ({ ...previous, [metric]: Number(event.target.value) }))} /><span>{metric === "latency_ms" ? "ms" : "drop"}</span></div></label>)}</div>
        {error && <div className="form-errors" role="alert">{error}</div>}
        <div className="compare-submit"><span><span className="info-dot">i</span> Missing metric data will be marked unavailable and excluded from findings.</span><Button disabled={busy || !previousId || !currentId}>{busy ? "Analyzing persisted runs…" : regressionMode ? <><ShieldAlert size={15} /> Check regressions</> : <><GitCompareArrows size={15} /> Compare runs</>}</Button></div>
      </form>}
    </Panel>

    {result && result.status === "incompatible" && <div className="incompatible-banner"><div className="incompatible-icon"><X size={17} /></div><div><strong>Comparison unavailable · incompatible runs</strong><p>The backend did not compare these runs because the selected data is not equivalent.</p><ul>{result.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></div></div>}
    {result && result.status === "compatible" && <>
      <div className="result-summary"><div className={`result-mark ${findings.length ? "has-findings" : "clean"}`}>{findings.length ? <ShieldAlert size={18} /> : <Check size={18} />}</div><div><strong>{regressionMode ? findings.length ? `${findings.length} regression finding${findings.length === 1 ? "" : "s"}` : availableCount ? "No regression detected" : "Insufficient measurements" : "Runs are compatible"}</strong><small>{regressionMode ? findings.length ? "One or more measured changes exceeded the configured threshold." : availableCount ? "Available measurements remained within all configured thresholds." : "No comparable measurements were available to determine regressions." : `${availableCount} metrics available · ${result.cases.length} compatible cases`}</small></div><StatusBadge status={result.status} /></div>
      {!regressionMode && <Panel><div className="panel-heading"><div><h2>Metric deltas</h2><p>Signed change = current minus previous. Direction indicates metric interpretation.</p></div></div><DataTable><thead><tr><th>Metric</th><th>Direction</th><th>Previous</th><th>Current</th><th>Difference</th><th>Absolute change</th><th>Threshold</th></tr></thead><tbody>{result.metrics.map((metric) => <tr key={metric.metric}><td><strong>{metricLabels[metric.metric] ?? metric.metric}</strong></td><td><span className={`direction-label ${metric.direction}`}>{metric.direction === "higher_is_better" ? <><ArrowUp size={13} /> Higher is better</> : <><ArrowDown size={13} /> Lower is better</>}</span></td><td>{metricValue(metric.previous_value, metric.metric)}</td><td>{metricValue(metric.current_value, metric.metric)}</td><td>{metric.difference === null ? "Unavailable" : `${metric.difference > 0 ? "+" : ""}${metric.metric === "latency_ms" ? `${metric.difference.toFixed(1)} ms` : `${(metric.difference * 100).toFixed(1)} pp`}`}</td><td>{metric.absolute_difference === null ? "Unavailable" : metric.metric === "latency_ms" ? `${metric.absolute_difference.toFixed(1)} ms` : `${(metric.absolute_difference * 100).toFixed(1)} pp`}</td><td>{thresholds[metric.metric as keyof typeof thresholds] === undefined ? "Not configured" : metric.metric === "latency_ms" ? `${thresholds.latency_ms} ms` : `${(thresholds[metric.metric as keyof typeof thresholds] * 100).toFixed(1)} pp`}</td></tr>)}</tbody></DataTable></Panel>}

      {regressionMode && <Panel><div className="panel-heading"><div><h2>Regression findings</h2><p>Only findings returned by the configured backend thresholds are listed.</p></div></div>{findings.length ? <DataTable><thead><tr><th>Metric</th><th>Previous</th><th>Current</th><th>Change</th><th>Threshold</th><th>Direction</th></tr></thead><tbody>{findings.map((item) => <tr key={item.metric}><td><strong>{metricLabels[item.metric] ?? item.metric}</strong></td><td>{metricValue(item.previous_value, item.metric)}</td><td>{metricValue(item.current_value, item.metric)}</td><td className="regression-delta">{item.difference > 0 ? "+" : ""}{item.metric === "latency_ms" ? `${item.difference.toFixed(1)} ms` : `${(item.difference * 100).toFixed(1)} pp`}</td><td>{item.metric === "latency_ms" ? `${item.threshold} ms` : `${(item.threshold * 100).toFixed(1)} pp`}</td><td>{item.direction.replaceAll("_", " ")}</td></tr>)}</tbody></DataTable> : <EmptyState title={availableCount ? "No threshold breach detected" : "Insufficient measurements"} description={availableCount ? "Available measurements did not exceed the configured regression thresholds." : "No comparable metric values were returned. A regression cannot be determined."} />}</Panel>}

      <Panel><div className="panel-heading"><div><h2>Case-level changes</h2><p>Output values are loaded from the selected persisted run details.</p></div></div>{result.cases.length ? <div className="case-list">{result.cases.map((item) => <article className="case-detail comparison-case" key={item.dataset_case_id}><header><div><strong>{item.name}</strong>{item.newly_failed && <span className="mini-chip danger">Newly failed</span>}{item.recovered && <span className="mini-chip positive">Recovered</span>}{item.output_changed && <span className="mini-chip">Output changed</span>}</div><span className="case-score-delta">{item.score_difference === null ? "Score unavailable" : `Score ${item.score_difference > 0 ? "+" : ""}${item.score_difference.toFixed(3)}`}</span></header><div className="comparison-statuses"><span>Previous <StatusBadge status={item.previous_status} /></span><span>Current <StatusBadge status={item.current_status} /></span></div>{item.output_changed && <div className="code-grid"><div><small>PREVIOUS OUTPUT</small><pre>{caseOutputs.before.get(item.dataset_case_id) ?? "No output recorded"}</pre></div><div><small>CURRENT OUTPUT</small><pre>{caseOutputs.after.get(item.dataset_case_id) ?? "No output recorded"}</pre></div></div>}</article>)}</div> : <EmptyState title="No case comparisons returned" description="No compatible cases were available." />}</Panel>
      <div className="comparison-run-links"><Link to={`/runs/${result.previous_run_id}`}>Previous run details <ArrowRight size={14} /></Link><Link to={`/runs/${result.current_run_id}`}>Current run details <ArrowRight size={14} /></Link></div>
    </>}
  </div>;
}
