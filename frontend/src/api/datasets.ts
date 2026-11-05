import { request } from "./client";
import type {
  Dataset,
  DatasetImportPreview,
  DatasetImportResult,
  DatasetListItem,
  DatasetValidation,
} from "./types";

export interface DatasetCaseInput {
  name: string;
  input_data: Record<string, unknown>;
  expected_output?: string | null;
  expected_json: boolean;
  reference_keywords?: string[] | null;
}

export interface DatasetInput {
  name: string;
  description?: string | null;
  cases: DatasetCaseInput[];
}

export const datasetsApi = {
  list: (skip = 0, limit = 100, signal?: AbortSignal) =>
    request<DatasetListItem[]>({ url: "/datasets", params: { skip, limit }, signal }),
  get: (id: string, signal?: AbortSignal) =>
    request<Dataset>({ url: `/datasets/${id}`, signal }),
  validate: (body: DatasetInput, signal?: AbortSignal) =>
    request<DatasetValidation>({ url: "/datasets/validate", method: "POST", data: body, signal }),
  create: (body: DatasetInput, signal?: AbortSignal) =>
    request<Dataset>({ url: "/datasets", method: "POST", data: body, signal }),
  importColumns: (file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<{ columns: string[]; max_bytes: number; max_cases: number }>({
      url: "/datasets/import/columns",
      method: "POST",
      data,
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  previewImport: (file: File, mapping?: Record<string, string>) => {
    const data = new FormData();
    data.append("file", file);
    if (mapping) data.append("column_mapping", JSON.stringify(mapping));
    return request<DatasetImportPreview>({
      url: "/datasets/import/preview",
      method: "POST",
      data,
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  import: (
    file: File,
    name: string,
    description: string,
    invalidPolicy: "reject" | "valid_only",
    mapping: Record<string, string> | undefined,
    idempotencyKey: string,
  ) => {
    const data = new FormData();
    data.append("file", file);
    data.append("name", name);
    if (description) data.append("description", description);
    data.append("invalid_policy", invalidPolicy);
    if (mapping) data.append("column_mapping", JSON.stringify(mapping));
    return request<DatasetImportResult>({
      url: "/datasets/import",
      method: "POST",
      data,
      headers: { "Content-Type": "multipart/form-data", "Idempotency-Key": idempotencyKey },
    });
  },
  validateStored: (id: string) =>
    request<{ dataset_id: string; valid_cases: number; invalid_cases: number; duplicate_identifiers: number; errors: Array<{ row: number; case_id: string | null; message: string }> }>({
      url: `/datasets/${id}/validate`,
      method: "POST",
    }),
};
