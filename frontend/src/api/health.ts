import { request } from "./client";
import type { Health } from "./types";

export const healthApi = {
  live: (signal?: AbortSignal) => request<Health>({ url: "/health", signal }),
  ready: (signal?: AbortSignal) => request<Health>({ url: "/health/ready", signal }),
};
