import { request } from "./client";
import type { AIProject, AIProjectInput, EvaluationRun } from "./types";

export const projectsApi = {
  list: (signal?: AbortSignal) =>
    request<AIProject[]>({ url: "/projects", signal }),
  create: (data: AIProjectInput) =>
    request<AIProject>({ url: "/projects", method: "POST", data }),
  start: (project_id: string, dataset_id: string, name?: string) =>
    request<{ run_id: string; status: EvaluationRun["status"] }>({
      url: "/projects/evaluations",
      method: "POST",
      data: { project_id, dataset_id, ...(name ? { name } : {}) },
    }),
};
