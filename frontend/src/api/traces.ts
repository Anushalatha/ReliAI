import { request } from "./client";
import type { Trace } from "./types";

export const tracesApi = {
  listForRun: (runId: string, signal?: AbortSignal) =>
    request<Trace[]>({ url: `/runs/${runId}/traces`, signal }),
  get: (runId: string, traceId: string, signal?: AbortSignal) =>
    request<Trace>({ url: `/runs/${runId}/traces/${traceId}`, signal }),
};
