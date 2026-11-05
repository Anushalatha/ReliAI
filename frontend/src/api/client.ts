import axios, { AxiosError, type AxiosRequestConfig } from "axios";

export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8002").replace(/\/$/, "");

export const http = axios.create({
  baseURL: apiBaseUrl,
  timeout: 12_000,
  headers: { "Content-Type": "application/json" },
});

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly requestId?: string,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  try {
    const response = await http.request<T>(config);
    return response.data;
  } catch (error) {
    if (axios.isCancel(error)) throw error;
    const axiosError = error as AxiosError<{ error?: { message?: string; request_id?: string; details?: unknown } }>;
    const body = axiosError.response?.data;
    const message = body?.error?.message ?? axiosError.message ?? "Request failed";
    throw new ApiError(
      message,
      axiosError.response?.status,
      body?.error?.request_id ?? axiosError.response?.headers["x-request-id"],
      body?.error?.details,
    );
  }
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.requestId ? `${error.message} · Request ID ${error.requestId}` : error.message;
  }
  if (error instanceof Error) return error.message;
  return "Unexpected error";
}
