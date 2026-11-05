import { useState, type FormEvent } from "react";
import { ArrowRight, Play, Plus, Server } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { datasetsApi } from "../api/datasets";
import { errorMessage } from "../api/client";
import { projectsApi } from "../api/projects";
import { runsApi } from "../api/runs";
import type { AIProject, EvaluationRun } from "../api/types";
import { usePolling } from "../hooks/usePolling";
import { Button, DataTable, EmptyState, ErrorState, formatDate, Loading, Modal, PageHeading, Panel, StatusBadge, notify, shortId } from "../components/ui";

const defaultTemplate = JSON.stringify({ prompt: "{{input_data.prompt}}" }, null, 2);

function RegisterProject({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [template, setTemplate] = useState(defaultTemplate);
  const [responsePath, setResponsePath] = useState("output");
  const [authEnvVar, setAuthEnvVar] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const requestTemplate: unknown = JSON.parse(template);
      if (typeof requestTemplate !== "object" || requestTemplate === null || Array.isArray(requestTemplate)) {
        throw new Error("Request template must be a JSON object.");
      }
      await projectsApi.create({
        name: name.trim(),
        endpoint_url: endpoint.trim(),
        http_method: "POST",
        request_template: requestTemplate as Record<string, unknown>,
        response_path: responsePath.trim(),
        ...(authEnvVar.trim() ? { auth_env_var: authEnvVar.trim() } : {}),
      });
      notify("AI project endpoint registered");
      onCreated();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  };

  return <Modal title="Register AI project" description="HTTPS targets require an explicit host allowlist. Local Docker HTTP targets require an exact endpoint allowlist and approved Docker network." onClose={onClose}>
    <form className="form-stack" onSubmit={submit}>
      <label className="field"><span>Project name <b>*</b></span><input required maxLength={200} value={name} onChange={(event) => setName(event.target.value)} placeholder="Support assistant API" /></label>
      <label className="field"><span>Authorized endpoint <b>*</b></span><input required type="url" value={endpoint} onChange={(event) => setEndpoint(event.target.value)} placeholder="https://api.example.com/v1/generate or http://knowledgeops-backend-1:8000/ask" /><small>Local HTTP is accepted only for an exact operator-allowlisted Docker service endpoint on its configured network. Other private, localhost, metadata, IP-literal, unlisted, and redirect destinations stay blocked.</small></label>
      <label className="field"><span>Request body template · JSON</span><textarea className="code-input" required value={template} onChange={(event) => setTemplate(event.target.value)} /><small>Use exact-value placeholders such as {"{{input_data.prompt}}"} or {"{{input_data}}"}.</small></label>
      <label className="field"><span>Response extraction path</span><input required value={responsePath} onChange={(event) => setResponsePath(event.target.value)} placeholder="result.answer" /><small>Use a dot path into the JSON response, `$` for the whole JSON response, or `text` for plain response text.</small></label>
      <label className="field"><span>Backend auth environment variable <small>Optional</small></span><input value={authEnvVar} onChange={(event) => setAuthEnvVar(event.target.value)} placeholder="MY_PROJECT_API_TOKEN" /><small>Only the variable name is stored. Set the secret in the backend environment.</small></label>
      {error && <div className="form-errors" role="alert">{error}</div>}
      <div className="modal-actions"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button disabled={busy || !endpoint.trim()}>{busy ? "Registering endpoint…" : "Register project"}</Button></div>
    </form>
  </Modal>;
}

export default function Projects() {
  const navigate = useNavigate();
  const projectsQuery = usePolling((signal) => projectsApi.list(signal), 15_000);
  const datasetsQuery = usePolling((signal) => datasetsApi.list(0, 100, signal), 30_000);
  const runsQuery = usePolling((signal) => runsApi.list(0, 100, signal), 5_000);
  const [registering, setRegistering] = useState(false);
  const [projectId, setProjectId] = useState("");
  const [datasetId, setDatasetId] = useState("");
  const [name, setName] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const projects = projectsQuery.data ?? [];
  const datasets = datasetsQuery.data ?? [];
  const projectRuns = (runsQuery.data ?? []).filter((run) => run.project_id);
  const runningCount = projectRuns.filter((run) => run.status === "running").length;

  const start = async (event: FormEvent) => {
    event.preventDefault();
    if (!projectId || !datasetId) return;
    setStarting(true);
    setError("");
    try {
      const accepted = await projectsApi.start(projectId, datasetId, name.trim() || undefined);
      notify("Project evaluation started; results are saved as a normal ReliAI run.");
      navigate(`/runs/${accepted.run_id}`);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setStarting(false);
    }
  };

  return <div className="page-stack">
    <PageHeading eyebrow="PROJECTS / HTTP INTEGRATION" title="Test your AI project" description="Evaluate the actual inference endpoint of an explicitly authorized AI application against reusable datasets." action={<Button onClick={() => setRegistering(true)}><Plus size={15} /> Register project</Button>} />
    <div className="info-box"><Server size={16} /><span>Credentials stay in the backend environment. HTTPS targets are host-allowlisted and pinned to public IPs; local Docker targets require an exact endpoint and approved network. Redirects are disabled. No uploaded code is executed.</span></div>
    <Panel>
      <div className="panel-heading"><div><h2>Start project evaluation</h2><p>Runs asynchronously with bounded concurrency and per-case progress.</p></div><span className="table-count">{runningCount} active</span></div>
      {projectsQuery.loading && !projectsQuery.data ? <Loading label="Loading registered projects" />
        : projectsQuery.error && !projectsQuery.data ? <ErrorState message={errorMessage(projectsQuery.error)} retry={projectsQuery.refresh} />
          : datasetsQuery.loading && !datasetsQuery.data ? <Loading label="Loading saved datasets" />
            : datasetsQuery.error && !datasetsQuery.data ? <ErrorState message={errorMessage(datasetsQuery.error)} retry={datasetsQuery.refresh} />
              : projects.length === 0 ? <EmptyState title="No AI projects registered" description="Register an HTTPS endpoint or explicitly authorized local Docker endpoint." action={<Button onClick={() => setRegistering(true)}><Plus size={15} /> Register project</Button>} />
                : datasets.length === 0 ? <EmptyState title="No datasets available" description="Import or create a reusable dataset before running project evaluations." action={<Link className="text-link" to="/datasets">Open datasets</Link>} />
                  : <form className="form-stack" onSubmit={start}>
                    <div className="form-grid">
                      <label className="field"><span>AI project <b>*</b></span><select required value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">Select a registered endpoint…</option>{projects.map((project) => <option value={project.id} key={project.id}>{project.name} · {new URL(project.endpoint_url).host}</option>)}</select></label>
                      <label className="field"><span>Dataset <b>*</b></span><select required value={datasetId} onChange={(event) => setDatasetId(event.target.value)}><option value="">Select a saved dataset…</option>{datasets.map((dataset) => <option value={dataset.id} key={dataset.id}>{dataset.name} · {dataset.case_count.toLocaleString()} cases</option>)}</select></label>
                    </div>
                    <label className="field"><span>Evaluation name <small>Optional</small></span><input maxLength={200} value={name} onChange={(event) => setName(event.target.value)} placeholder="Defaults to dataset · project name" /></label>
                    {error && <div className="form-errors" role="alert">{error}</div>}
                    <Button disabled={starting || !projectId || !datasetId}>{starting ? "Starting evaluation…" : <><Play size={15} /> Start evaluation</>}</Button>
                  </form>}
    </Panel>
    <Panel className="table-panel">
      <div className="panel-heading"><div><h2>Registered endpoints</h2><p>Only non-secret request configuration is stored and shown.</p></div></div>
      {projects.length > 0 && <DataTable><thead><tr><th>Project</th><th>Endpoint</th><th>Method</th><th>Authentication</th><th>Registered</th></tr></thead><tbody>{projects.map((project: AIProject) => <tr key={project.id}><td><strong>{project.name}</strong></td><td><code>{project.endpoint_url}</code></td><td>{project.http_method}</td><td>{project.auth_env_var ? `Backend env · ${project.auth_env_var}` : "None configured"}</td><td>{formatDate(project.created_at)}</td></tr>)}</tbody></DataTable>}
      {!projectsQuery.loading && !projects.length && <span className="unavailable">No endpoints registered.</span>}
    </Panel>
    <Panel className="table-panel">
      <div className="panel-heading"><div><h2>Recent project runs</h2><p>Progress and final case-level outputs are available in the persisted run detail.</p></div></div>
      {runsQuery.error && !runsQuery.data ? <ErrorState message={errorMessage(runsQuery.error)} retry={runsQuery.refresh} />
        : projectRuns.length ? <DataTable><thead><tr><th>Run</th><th>Status</th><th>Provider</th><th>Created</th><th /></tr></thead><tbody>{projectRuns.map((run: EvaluationRun) => <tr key={run.id}><td><Link className="table-primary" to={`/runs/${run.id}`}><strong>{run.name}</strong><small>{shortId(run.id)}</small></Link></td><td><StatusBadge status={run.status} /></td><td>{run.model_name}</td><td>{formatDate(run.created_at)}</td><td><Link className="icon-link" to={`/runs/${run.id}`} aria-label="Inspect project run"><ArrowRight size={15} /></Link></td></tr>)}</tbody></DataTable>
          : !runsQuery.loading && <EmptyState title="No project evaluations yet" description="Start an evaluation above to test an authorized endpoint." />}
    </Panel>
    {registering && <RegisterProject onClose={() => setRegistering(false)} onCreated={() => { setRegistering(false); void projectsQuery.refresh(); }} />}
  </div>;
}
