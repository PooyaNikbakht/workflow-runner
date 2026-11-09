import { site } from "@/config/site";
import type {
  AppConfig,
  Delivery,
  Json,
  ReviewPayload,
  Run,
  RunSummary,
  Workflow,
} from "@/lib/types";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public fields: { field: string; message: string }[] = [],
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${site.apiUrl}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Can't reach the API. Is it running on port 8050?", 0);
  }
  if (!res.ok) {
    let message = `Request failed (${res.status}).`;
    let fields: { field: string; message: string }[] = [];
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      if (Array.isArray(body.errors)) fields = body.errors;
    } catch {
      // keep the generic message
    }
    throw new ApiError(message, res.status, fields);
  }
  return res.json() as Promise<T>;
}

export const api = {
  config: () => request<AppConfig>("/api/config"),
  workflows: () => request<Workflow[]>("/api/workflows"),
  runs: () => request<RunSummary[]>("/api/runs?limit=30"),
  run: (id: string) => request<Run>(`/api/runs/${id}`),
  startRun: (workflow: string, input: Json) =>
    request<{ id: string }>("/api/runs", {
      method: "POST",
      body: JSON.stringify({ workflow, input }),
    }),
  review: (id: string, payload: ReviewPayload) =>
    request<{ status: string }>(`/api/runs/${id}/review`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deliveries: () => request<Delivery[]>("/api/receiver/deliveries"),
  eventsUrl: (id: string) => `${site.apiUrl}/api/runs/${id}/events`,
};
