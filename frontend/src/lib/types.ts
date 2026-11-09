export type StepStatus =
  | "pending"
  | "queued"
  | "running"
  | "needs_review"
  | "completed"
  | "failed"
  | "skipped";
export type RunStatus = "queued" | "running" | "needs_review" | "completed" | "failed" | "rejected";
export type StepKind = "action" | "llm" | "review" | "webhook";

export type Json = Record<string, unknown>;

export interface Step {
  key: string;
  title: string;
  kind: StepKind;
  description: string;
  status: StepStatus;
  attempts: number;
  max_attempts: number;
  output: Json | null;
  error: string | null;
  started_at: number | null;
  finished_at: number | null;
  next_attempt_at: number | null;
}

export interface Run {
  id: string;
  workflow: string;
  workflow_name: string;
  title: string;
  status: RunStatus;
  input: Json;
  error: string | null;
  created_at: number;
  updated_at: number;
  finished_at: number | null;
  last_event_id: number | null;
  steps: Step[];
}

export interface RunSummary {
  id: string;
  workflow: string;
  workflow_name: string;
  title: string;
  status: RunStatus;
  created_at: number;
  finished_at: number | null;
  steps_done: number;
  steps_total: number;
  retries: number;
}

export interface LogEvent {
  id: number;
  ts: number;
  kind: "log" | "state";
  level: "debug" | "info" | "warn" | "error";
  step: string | null;
  message: string;
  data: Json | null;
}

export interface Sample {
  label: string;
  input: Json;
}

export interface Workflow {
  key: string;
  name: string;
  description: string;
  steps: { key: string; title: string; kind: StepKind; description: string }[];
  samples: Sample[];
}

export interface AppConfig {
  provider: "anthropic" | "offline";
  model: string;
  demo_mode: boolean;
  webhook_url: string;
}

export interface Delivery {
  id: number;
  idempotency_key: string;
  received_at: number;
  last_received_at: number;
  attempts: number;
  signature_ok: boolean;
  event: string | null;
  payload: {
    id: string;
    event: string;
    created_at: number;
    data: { to?: { name: string; email: string }; subject?: string; body?: string } & Json;
  };
}

export interface ReviewPayload {
  decision: "approve" | "edit" | "reject";
  edits?: { subject: string; body: string };
  note?: string;
}
