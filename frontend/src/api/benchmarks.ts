import { request } from "./client";
import type { BenchmarkDetail, BenchmarkListItem, BenchmarkSummary } from "./types";

export interface BenchmarkInput {
  dataset_id: string;
  name?: string;
  providers: Array<"mock" | "groq">;
  groq_model?: string;
}

export const benchmarksApi = {
  list: (skip = 0, limit = 100, signal?: AbortSignal) =>
    request<BenchmarkListItem[]>({ url: "/benchmarks", params: { skip, limit }, signal }),
  get: (id: string, signal?: AbortSignal) =>
    request<BenchmarkDetail>({ url: `/benchmarks/${id}`, signal }),
  summary: (limit = 30, signal?: AbortSignal) =>
    request<BenchmarkSummary>({ url: "/benchmarks/summary", params: { limit }, signal }),
  create: (data: BenchmarkInput) =>
    request<BenchmarkDetail>({ url: "/benchmarks", method: "POST", data }),
};
