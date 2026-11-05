import { useMemo, useState, type FormEvent } from "react";
import { ArrowLeft, ChevronLeft, ChevronRight, Database, Download, Plus, Search, Trash2, Upload } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { datasetsApi, type DatasetInput, type DatasetCaseInput } from "../api/datasets";
import { errorMessage } from "../api/client";
import type { Dataset, DatasetImportPreview } from "../api/types";
import { usePolling } from "../hooks/usePolling";
import { Button, CopyButton, DataTable, EmptyState, ErrorState, formatDate, Loading, Modal, PageHeading, Panel, shortId, StatusBadge, notify } from "../components/ui";

const blankCase = (): DatasetCaseInput => ({ name: "", input_data: { prompt: "" }, expected_output: "", expected_json: false, reference_keywords: [] });

function csvCell(value: string) {
  const safe = /^[=+\-@]/.test(value) ? `'${value}` : value;
  return `"${safe.replaceAll('"', '""')}"`;
}

function downloadImportReport(preview: DatasetImportPreview) {
  const rows = [["row", "case_id", "error"], ...preview.errors.map((issue) => [
    String(issue.row),
    issue.case_id ?? "",
    issue.message,
  ])];
  const blob = new Blob([rows.map((row) => row.map(csvCell).join(",")).join("\r\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${preview.file_name}.import-errors.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

function UploadDatasetModal({ onClose, onCreated }: { onClose: () => void; onCreated: (dataset: Dataset) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [columns, setColumns] = useState<string[]>([]);
  const [preview, setPreview] = useState<DatasetImportPreview | null>(null);
  const [invalidPolicy, setInvalidPolicy] = useState<"reject" | "valid_only">("reject");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [idempotencyKey, setIdempotencyKey] = useState("");

  const selectFile = async (selected: File | null) => {
    setFile(selected);
    setPreview(null);
    setColumns([]);
    setMapping({});
    setError("");
    setIdempotencyKey(crypto.randomUUID());
    if (!selected) return;
    setName((current) => current || selected.name.replace(/\.[^.]+$/, ""));
    if (/\.csv$/i.test(selected.name)) {
      try {
        const result = await datasetsApi.importColumns(selected);
        setColumns(result.columns);
        const findColumn = (...names: string[]) =>
          result.columns.find((column) => names.includes(column.trim().toLowerCase())) ?? "";
        setMapping({
          input_data: findColumn("input_data", "input", "prompt", "query", "text"),
          name: findColumn("name", "case_id", "id"),
          expected_output: findColumn("expected_output", "expected", "answer", "target"),
          reference_keywords: findColumn("reference_keywords", "keywords"),
          expect_valid_json: findColumn("expect_valid_json", "expected_json"),
        });
      } catch (reason) {
        setError(errorMessage(reason));
      }
    }
  };

  const previewFile = async () => {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const selectedMapping = columns.length
        ? Object.fromEntries(Object.entries(mapping).filter(([, column]) => Boolean(column)))
        : undefined;
      const result = await datasetsApi.previewImport(file, selectedMapping);
      setPreview(result);
    } catch (reason) {
      setError(errorMessage(reason));
      setPreview(null);
    } finally {
      setBusy(false);
    }
  };

  const importFile = async () => {
    if (!file || !preview || !name.trim()) return;
    setBusy(true);
    setError("");
    try {
      const selectedMapping = columns.length
        ? Object.fromEntries(Object.entries(mapping).filter(([, column]) => Boolean(column)))
        : undefined;
      const result = await datasetsApi.import(
        file,
        name.trim(),
        description.trim(),
        invalidPolicy,
        selectedMapping,
        idempotencyKey,
      );
      notify(
        result.duplicate_submission
          ? "This upload was already imported; no new cases were created."
          : `Imported ${result.created_cases} cases${result.rejected_cases ? `; skipped ${result.rejected_cases} invalid rows` : ""}.`,
      );
      onCreated(result.dataset);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  };

  const mappingFields: Array<[keyof typeof mapping, string, boolean]> = [
    ["input_data", "Input data", true],
    ["name", "Case name / ID", false],
    ["expected_output", "Expected output", false],
    ["reference_keywords", "Reference keywords", false],
    ["expect_valid_json", "Expect valid JSON", false],
  ];

  return <Modal title="Upload dataset" description="Import CSV, JSON, JSONL, or NDJSON. Preview and validate every row before saving." onClose={onClose}>
    <div className="form-stack">
      <label className="field"><span>Dataset file <b>*</b></span><input type="file" accept=".csv,.json,.jsonl,.ndjson" onChange={(event) => void selectFile(event.target.files?.[0] ?? null)} /></label>
      {file && <div className="info-box">{file.name} · {(file.size / 1024).toFixed(1)} KB</div>}
      {columns.length > 0 && <fieldset className="form-grid">
        <legend>CSV column mapping</legend>
        {mappingFields.map(([key, label, required]) => <label className="field" key={key}>
          <span>{label}{required && <b> *</b>}</span>
          <select required={required} value={mapping[key]} onChange={(event) => setMapping((current) => ({ ...current, [key]: event.target.value }))}>
            <option value="">Not mapped</option>
            {columns.map((column) => <option value={column} key={column}>{column}</option>)}
          </select>
        </label>)}
      </fieldset>}
      <div className="form-grid">
        <label className="field"><span>Dataset name <b>*</b></span><input required maxLength={200} value={name} onChange={(event) => setName(event.target.value)} /></label>
        <label className="field"><span>Description</span><input value={description} onChange={(event) => setDescription(event.target.value)} /></label>
      </div>
      <label className="field"><span>Invalid row policy</span><select value={invalidPolicy} onChange={(event) => setInvalidPolicy(event.target.value as "reject" | "valid_only")}><option value="reject">Reject entire import if any row is invalid</option><option value="valid_only">Import valid rows only and retain the error report</option></select></label>
      {preview && <Panel className="import-preview">
        <div className="panel-heading"><div><h2>Import preview</h2><p>{preview.file_name} · {preview.format.toUpperCase()} · max {preview.max_cases.toLocaleString()} cases / {(preview.max_bytes / (1024 * 1024)).toFixed(0)} MB</p></div></div>
        <div className="metric-grid">
          <div className="aggregate-metric"><span>Total rows</span><strong>{preview.total_rows}</strong></div>
          <div className="aggregate-metric"><span>Valid cases</span><strong>{preview.valid_cases}</strong></div>
          <div className="aggregate-metric"><span>Invalid cases</span><strong>{preview.invalid_cases}</strong></div>
          <div className="aggregate-metric"><span>Missing expected output</span><strong>{preview.missing_expected_outputs}</strong></div>
          <div className="aggregate-metric"><span>Duplicate identifiers</span><strong>{preview.duplicate_identifiers}</strong></div>
        </div>
        {preview.errors.length > 0 && <div className="form-errors" role="alert">
          <strong>Invalid rows</strong>
          <div>{preview.errors.slice(0, 30).map((issue) => <div key={`${issue.row}-${issue.message}`}>Row {issue.row}{issue.case_id ? ` · ${issue.case_id}` : ""}: {issue.message}</div>)}</div>
          {preview.errors.length > 30 && <small>Showing 30 of {preview.errors.length} errors. Download the report for all rows.</small>}
          <Button type="button" variant="secondary" onClick={() => downloadImportReport(preview)}><Download size={14} /> Download error report</Button>
        </div>}
        {preview.sample_cases.length > 0 && <div className="case-list"><strong>Valid case sample</strong>{preview.sample_cases.map((item) => <details className="case-detail" key={item.name}><summary>{item.name} · {item.expected_output === null ? "no expected output" : "expected output provided"}</summary><div className="code-grid"><div><small>INPUT</small><pre>{JSON.stringify(item.input_data, null, 2)}</pre></div><div><small>EXPECTED OUTPUT</small><pre>{item.expected_output ?? "Not provided"}</pre></div></div></details>)}</div>}
      </Panel>}
      {error && <div className="form-errors" role="alert">{error}</div>}
      <div className="modal-actions">
        <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
        <Button type="button" variant="secondary" disabled={!file || busy || (columns.length > 0 && !mapping.input_data)} onClick={() => void previewFile()}>{busy && !preview ? "Validating…" : "Preview & validate"}</Button>
        <Button type="button" disabled={!file || !preview || preview.valid_cases === 0 || busy || (invalidPolicy === "reject" && preview.invalid_cases > 0)} onClick={() => void importFile()}>{busy && preview ? "Importing…" : "Create dataset"}</Button>
      </div>
    </div>
  </Modal>;
}

function DatasetForm({ onClose, onCreated }: { onClose: () => void; onCreated: (dataset: Dataset) => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [cases, setCases] = useState<DatasetCaseInput[]>([blankCase()]);
  const [inputTexts, setInputTexts] = useState<string[]>([JSON.stringify({ prompt: "" }, null, 2)]);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const editCase = (index: number, patch: Partial<DatasetCaseInput>) => {
    setCases((items) => items.map((item, current) => current === index ? { ...item, ...patch } : item));
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setErrors([]);
    let parsedInputs: Record<string, unknown>[];
    try {
      parsedInputs = inputTexts.map((text, index) => {
        const parsed: unknown = JSON.parse(text);
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          throw new Error(`Case ${index + 1}: input data must be a JSON object`);
        }
        return parsed as Record<string, unknown>;
      });
    } catch (reason) {
      setErrors([reason instanceof Error ? reason.message : "Input data must be valid JSON"]);
      setBusy(false);
      return;
    }
    const body: DatasetInput = {
      name: name.trim(),
      description: description.trim() || null,
      cases: cases.map((item, index) => {
        const keywords = item.reference_keywords?.filter(Boolean) ?? [];
        return {
          ...item,
          name: item.name.trim(),
          input_data: parsedInputs[index],
          expected_output: item.expected_output || null,
          reference_keywords: keywords.length ? keywords : null,
        };
      }),
    };
    try {
      const validation = await datasetsApi.validate(body);
      if (!validation.valid) {
        setErrors(validation.errors.map((error) => `${error.location.join(".")}: ${error.message}`));
        return;
      }
      const dataset = await datasetsApi.create(body);
      notify("Dataset created and saved");
      onCreated(dataset);
    } catch (error) {
      setErrors([errorMessage(error)]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Create dataset" description="Define repeatable cases for deterministic evaluation." onClose={onClose}>
      <form className="form-stack" onSubmit={submit}>
        <div className="form-grid">
          <label className="field"><span>Dataset name <b>*</b></span><input required maxLength={200} value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Support response quality" /></label>
          <label className="field"><span>Description</span><input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What are you evaluating?" /></label>
        </div>
        <div className="case-builder-heading"><div><strong>Evaluation cases</strong><small>Input JSON is sent to the configured provider.</small></div><Button type="button" variant="secondary" onClick={() => { setCases((items) => [...items, blankCase()]); setInputTexts((items) => [...items, JSON.stringify({ prompt: "" }, null, 2)]); }}><Plus size={14} /> Add case</Button></div>
        <div className="case-builder-list">
          {cases.map((item, index) => <fieldset className="case-builder" key={index}>
            <legend>CASE {String(index + 1).padStart(2, "0")}</legend>
            {cases.length > 1 && <button type="button" className="icon-button case-remove" aria-label="Remove case" onClick={() => { setCases((items) => items.filter((_, current) => current !== index)); setInputTexts((items) => items.filter((_, current) => current !== index)); }}><Trash2 size={15} /></button>}
            <div className="form-grid">
              <label className="field"><span>Case name <b>*</b></span><input required maxLength={200} value={item.name} onChange={(event) => editCase(index, { name: event.target.value })} placeholder="Case name" /></label>
              <label className="field"><span>Expected output</span><input value={item.expected_output ?? ""} onChange={(event) => editCase(index, { expected_output: event.target.value })} placeholder="Optional reference answer" /></label>
            </div>
            <label className="field"><span>Input data · JSON <b>*</b></span><textarea className="code-input" required value={inputTexts[index]} onChange={(event) => setInputTexts((items) => items.map((value, current) => current === index ? event.target.value : value))} /></label>
            <div className="form-grid case-options">
              <label className="field"><span>Reference keywords</span><input value={item.reference_keywords?.join(", ") ?? ""} onChange={(event) => editCase(index, { reference_keywords: event.target.value.split(",").map((word) => word.trim()).filter(Boolean) })} placeholder="accurate, concise" /><small>Comma-separated terms measured by substring coverage.</small></label>
              <label className="checkbox-field"><input type="checkbox" checked={item.expected_json} onChange={(event) => editCase(index, { expected_json: event.target.checked })} /><span><strong>Expect valid JSON</strong><small>Measure whether the response parses as JSON.</small></span></label>
            </div>
          </fieldset>)}
        </div>
        {errors.length > 0 && <div className="form-errors" role="alert">{errors.map((error, index) => <div key={`${error}-${index}`}>{error}</div>)}</div>}
        <div className="modal-actions"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" disabled={busy}>{busy ? "Validating and saving…" : "Validate & create"}</Button></div>
      </form>
    </Modal>
  );
}

export default function Datasets() {
  const { datasetId } = useParams();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [creating, setCreating] = useState(false);
  const [creatingImport, setCreatingImport] = useState(false);
  const listQuery = usePolling((signal) => datasetsApi.list(0, 100, signal), 30_000);
  const datasets = listQuery.data ?? [];
  const filtered = useMemo(() => datasets.filter((dataset) => `${dataset.name} ${dataset.description ?? ""} ${dataset.id}`.toLowerCase().includes(search.toLowerCase())), [datasets, search]);
  const pageSize = 10;
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const visible = filtered.slice(page * pageSize, (page + 1) * pageSize);

  if (datasetId) return <DatasetDetails key={datasetId} datasetId={datasetId} />;

  return <div className="page-stack">
    <PageHeading eyebrow="EVALUATION / DATASETS" title="Datasets" description="Curate repeatable evaluation cases and reference signals." action={<><Button variant="secondary" onClick={() => setCreatingImport(true)}><Upload size={15} /> Upload dataset</Button><Button onClick={() => setCreating(true)}><Plus size={16} /> Create manually</Button></>} />
    <Panel className="table-panel">
      <div className="table-toolbar"><label className="search-field"><Search size={16} /><input value={search} onChange={(event) => { setSearch(event.target.value); setPage(0); }} placeholder="Search datasets…" /></label><span className="table-count">{filtered.length} datasets</span></div>
      {Boolean(listQuery.error && listQuery.data) && <div className="inline-warning">Dataset refresh failed. Showing the last successfully loaded data.</div>}
      {listQuery.loading && !listQuery.data ? <Loading /> : listQuery.error && !listQuery.data ? <ErrorState message={errorMessage(listQuery.error)} retry={listQuery.refresh} /> : visible.length === 0 ? <EmptyState title={search ? "No matching datasets" : "No datasets yet"} description={search ? "Try another search term." : "Create a dataset manually or upload a CSV, JSON, or JSONL file."} action={!search && <Button onClick={() => setCreatingImport(true)}><Upload size={15} /> Upload dataset</Button>} /> : <DataTable><thead><tr><th>Dataset</th><th>Cases</th><th>Import</th><th>Created</th><th>Identifier</th><th /></tr></thead><tbody>{visible.map((dataset) => <tr key={dataset.id}><td><Link className="table-primary" to={`/datasets/${dataset.id}`}><span className="table-icon"><Database size={16} /></span><span><strong>{dataset.name}</strong><small>{dataset.description || "No description"}</small></span></Link></td><td><span className="case-count">{dataset.case_count} cases</span></td><td><span className="provider-cell"><StatusBadge status={dataset.import_status} /><small>{dataset.source_file_name ?? "Manual"}</small></span></td><td>{formatDate(dataset.created_at)}</td><td><span className="id-inline"><code>{shortId(dataset.id)}</code><CopyButton value={dataset.id} /></span></td><td><Link className="text-link" to={`/datasets/${dataset.id}`}>Inspect</Link></td></tr>)}</tbody></DataTable>}
      {filtered.length > pageSize && <div className="pagination"><span>Page {page + 1} of {pages}</span><div><Button variant="secondary" disabled={page === 0} onClick={() => setPage((value) => value - 1)}><ChevronLeft size={15} /> Previous</Button><Button variant="secondary" disabled={page >= pages - 1} onClick={() => setPage((value) => value + 1)}>Next <ChevronRight size={15} /></Button></div></div>}
    </Panel>
    {creating && <DatasetForm onClose={() => setCreating(false)} onCreated={(dataset) => { setCreating(false); void listQuery.refresh(); navigate(`/datasets/${dataset.id}`); }} />}
    {creatingImport && <UploadDatasetModal onClose={() => setCreatingImport(false)} onCreated={(dataset) => { setCreatingImport(false); void listQuery.refresh(); navigate(`/datasets/${dataset.id}`); }} />}
  </div>;
}

function DatasetDetails({ datasetId }: { datasetId: string }) {
  const navigate = useNavigate();
  const query = usePolling((signal) => datasetsApi.get(datasetId, signal));
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState<Awaited<ReturnType<typeof datasetsApi.validateStored>> | null>(null);
  const dataset = query.data;
  if (query.loading && !dataset) return <Loading label="Loading dataset details" />;
  if (query.error && !dataset) return <ErrorState message={errorMessage(query.error)} retry={query.refresh} />;
  if (!dataset) return <ErrorState message="Dataset not found." />;
  const validate = async () => {
    setValidating(true);
    try {
      setValidation(await datasetsApi.validateStored(datasetId));
    } catch (reason) {
      notify(errorMessage(reason), "error");
    } finally {
      setValidating(false);
    }
  };
  return <div className="page-stack">
    <button className="back-link" onClick={() => navigate("/datasets")}><ArrowLeft size={15} /> All datasets</button>
    <PageHeading eyebrow="DATASET / DETAIL" title={dataset.name} description={dataset.description ?? "No description provided."} action={<><CopyButton value={dataset.id} /><Button variant="secondary" disabled={validating} onClick={() => void validate()}>{validating ? "Validating…" : "Validate dataset"}</Button><Link className="button button-primary" to={`/runs?dataset=${dataset.id}`}>Run evaluation</Link></>} />
    {Boolean(query.error) && <div className="inline-warning">Dataset refresh failed. Showing the last successfully loaded data.</div>}
    <Panel className="detail-meta"><span><small>DATASET ID</small><code>{dataset.id}</code></span><span><small>CASES</small><strong>{dataset.cases.length}</strong></span><span><small>IMPORT STATUS</small><StatusBadge status={dataset.import_status} /></span><span><small>SOURCE FILE</small><strong>{dataset.source_file_name ?? "Manual creation"}</strong></span><span><small>CREATED</small><strong>{formatDate(dataset.created_at)}</strong></span></Panel>
    {validation && <Panel><div className="panel-heading"><div><h2>Validation result</h2><p>{validation.valid_cases} valid · {validation.invalid_cases} invalid · {validation.duplicate_identifiers} duplicate identifiers</p></div></div>{validation.errors.length > 0 && <div className="form-errors">{validation.errors.map((issue) => <div key={`${issue.row}-${issue.message}`}>Case {issue.row}{issue.case_id ? ` · ${issue.case_id}` : ""}: {issue.message}</div>)}</div>}{!validation.errors.length && <div className="info-box">All persisted cases passed validation.</div>}</Panel>}
    {dataset.validation_errors?.length ? <Panel><div className="panel-heading"><div><h2>Import validation report</h2><p>Rows skipped or rejected during import</p></div></div><div className="form-errors">{dataset.validation_errors.map((issue) => <div key={`${issue.row}-${issue.message}`}>Row {issue.row}{issue.case_id ? ` · ${issue.case_id}` : ""}: {issue.message}</div>)}</div></Panel> : null}
    <Panel><div className="panel-heading"><div><h2>Dataset cases</h2><p>Saved inputs and evaluation criteria</p></div></div><div className="case-list">{dataset.cases.map((item) => <article className="case-detail" key={item.id}><header><div><span className="case-position">{String(item.position + 1).padStart(2, "0")}</span><strong>{item.name}</strong></div><div className="chip-row">{item.expected_json && <span className="mini-chip">JSON expected</span>}{item.reference_keywords?.map((term) => <span className="mini-chip" key={term}>{term}</span>)}</div></header><div className="code-grid"><div><small>INPUT</small><pre>{JSON.stringify(item.input_data, null, 2)}</pre></div><div><small>REFERENCE OUTPUT</small><pre>{item.expected_output ?? "Not provided"}</pre></div></div></article>)}</div></Panel>
  </div>;
}
