import { request } from "./client";
import type { EvaluationProgress, EvaluationRun, RunComparison } from "./types";

export const runsApi = {
  list: (skip = 0, limit = 100, signal?: AbortSignal) =>
    request<EvaluationRun[]>({ url: "/runs", params: { skip, limit }, signal }),
  get: (id: string, signal?: AbortSignal) =>
    request<EvaluationRun>({ url: `/runs/${id}`, signal }),
  progress: (id: string, signal?: AbortSignal) =>
    request<EvaluationProgress>({ url: `/runs/${id}/progress`, signal }),
  start: (
    dataset_id: string,
    provider?: "mock" | "groq",
    signal?: AbortSignal,
  ) =>
    request<EvaluationRun>({
      url: "/runs",
      method: "POST",
      data: provider ? { dataset_id, provider } : { dataset_id },
      signal,
    }),
  compare: (
    previous_run_id: string,
    current_run_id: string,
    thresholds?: Record<string, number>,
    signal?: AbortSignal,
  ) =>
    request<RunComparison>({
      url: "/runs/compare",
      method: "POST",
      data: { previous_run_id, current_run_id, thresholds },
      signal,
    }),
  regressions: (
    run_id: string,
    baseline_run_id: string,
    thresholds?: Record<string, number>,
    signal?: AbortSignal,
  ) =>
    request<RunComparison>({
      url: `/runs/${run_id}/regressions`,
      method: "POST",
      data: { baseline_run_id, thresholds },
      signal,
    }),
};
