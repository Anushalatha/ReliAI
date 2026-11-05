export type RunStatus = "pending" | "running" | "completed" | "failed";
export type CaseStatus = RunStatus | "skipped";
export type TraceStatus = "running" | "succeeded" | "failed";

export interface DatasetCase {
  id: string;
  dataset_id: string;
  name: string;
  position: number;
  input_data: Record<string, unknown>;
  expected_output: string | null;
  expected_json: boolean;
  reference_keywords: string[] | null;
  metadata?: Record<string, unknown> | null;
  created_at: string;
}

export interface Dataset {
  id: string;
  name: string;
  description: string | null;
  source_file_name: string | null;
  import_status: string;
  validation_errors: DatasetImportIssue[] | null;
  created_at: string;
  cases: DatasetCase[];
}

export interface DatasetListItem {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  case_count: number;
  source_file_name: string | null;
  import_status: string;
}

export interface MetricValue {
  value: number | null;
  available: boolean;
}

export interface AggregateMetric {
  value: number | null;
  available_cases: number;
  total_cases: number;
}

export type CaseMetrics = Record<string, MetricValue>;
export type RunMetrics = Record<string, AggregateMetric>;

export interface EvaluationCase {
  id: string;
  run_id: string;
  name: string;
  dataset_case_id: string | null;
  status: CaseStatus;
  input_data: Record<string, unknown>;
  expected_output: string | null;
  expected_json: boolean;
  reference_keywords: string[] | null;
  actual_output: string | null;
  score: number | null;
  metrics: CaseMetrics | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface EvaluationRun {
  id: string;
  dataset_id: string | null;
  project_id?: string | null;
  name: string;
  status: RunStatus;
  provider: string | null;
  model_name: string | null;
  metrics: RunMetrics | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  cases?: EvaluationCase[];
}

export interface Trace {
  id: string;
  run_id: string;
  case_id: string | null;
  request_id: string | null;
  operation_name: string;
  status: TraceStatus;
  provider: string | null;
  model_name: string | null;
  started_at: string;
  completed_at: string | null;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  error_type: string | null;
  error_message: string | null;
  error_details: Record<string, unknown> | null;
  trace_metadata: Record<string, unknown> | null;
}

export interface MetricComparison {
  metric: string;
  direction: "higher_is_better" | "lower_is_better";
  previous_value: number | null;
  current_value: number | null;
  difference: number | null;
  absolute_difference: number | null;
  available: boolean;
}

export interface CaseComparison {
  dataset_case_id: string;
  name: string;
  previous_status: CaseStatus;
  current_status: CaseStatus;
  previous_score: number | null;
  current_score: number | null;
  score_difference: number | null;
  output_changed: boolean | null;
  newly_failed: boolean;
  recovered: boolean;
}

export interface RegressionFinding {
  metric: string;
  previous_value: number;
  current_value: number;
  difference: number;
  threshold: number;
  direction: "higher_is_better" | "lower_is_better";
}

export interface RunComparison {
  status: "compatible" | "incompatible";
  previous_run_id: string;
  current_run_id: string;
  reasons: string[];
  metrics: MetricComparison[];
  cases: CaseComparison[];
  regressions: RegressionFinding[];
}

export type BenchmarkStatus = "running" | "completed" | "partial" | "failed";

export interface BenchmarkListItem {
  id: string;
  dataset_id: string | null;
  name: string;
  status: BenchmarkStatus;
  providers: string[];
  created_at: string;
  completed_at: string | null;
}

export interface BenchmarkProviderResult {
  provider: string;
  models: string[];
  run_ids: string[];
  run_outcomes: { completed: number; failed: number; sample_count: number };
  quality_metrics: Record<string, { value: number | null; sample_count: number }>;
  latency: {
    average_ms: number | null;
    median_ms: number | null;
    p50_ms: number | null;
    p95_ms: number | null;
    sample_count: number;
    p95_minimum_samples: number;
  };
  input_tokens: {
    average_tokens: number | null;
    total_tokens: number | null;
    sample_count: number;
  };
  output_tokens: {
    average_tokens: number | null;
    total_tokens: number | null;
    sample_count: number;
  };
  case_outcomes: {
    attempts: number;
    successes: number;
    failures: number;
    success_rate: number | null;
    failure_rate: number | null;
    sample_count: number;
  };
  error_counts: Record<string, number>;
}

export interface BenchmarkDetail extends BenchmarkListItem {
  dataset_name: string | null;
  case_count: number;
  results: BenchmarkProviderResult[];
}

export interface BenchmarkSummary {
  provider_results: BenchmarkProviderResult[];
  recent_benchmarks: BenchmarkListItem[];
}

export interface DatasetValidation {
  valid: boolean;
  case_count: number | null;
  errors: Array<{ location: (string | number)[]; message: string; type: string }>;
}

export interface DatasetImportIssue {
  row: number;
  case_id: string | null;
  message: string;
}

export interface DatasetImportPreview {
  file_name: string;
  format: "csv" | "json" | "jsonl";
  total_rows: number;
  valid_cases: number;
  invalid_cases: number;
  missing_expected_outputs: number;
  duplicate_identifiers: number;
  columns: string[];
  max_bytes: number;
  max_cases: number;
  errors: DatasetImportIssue[];
  sample_cases: Array<{
    name: string;
    input_data: Record<string, unknown>;
    expected_output: string | null;
    expected_json: boolean;
    reference_keywords: string[] | null;
    metadata?: Record<string, unknown> | null;
  }>;
}

export interface DatasetImportResult {
  dataset: Dataset;
  created_cases: number;
  rejected_cases: number;
  duplicate_submission: boolean;
}

export interface AIProject {
  id: string;
  name: string;
  endpoint_url: string;
  http_method: "POST" | "PUT";
  request_template: Record<string, unknown>;
  response_path: string;
  auth_env_var: string | null;
  auth_header: string;
  auth_scheme: string;
  created_at: string;
}

export interface AIProjectInput {
  name: string;
  endpoint_url: string;
  http_method: "POST" | "PUT";
  request_template: Record<string, unknown>;
  response_path: string;
  auth_env_var?: string | null;
}

export interface EvaluationProgress {
  id: string;
  status: RunStatus;
  total_cases: number;
  completed_cases: number;
  failed_cases: number;
  pending_cases: number;
}

export interface Health {
  status: string;
  database?: string;
}
