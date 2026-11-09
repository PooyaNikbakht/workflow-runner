import type { RunStatus, StepStatus } from "@/lib/types";

export const STEP_LABEL: Record<StepStatus, string> = {
  pending: "Pending",
  queued: "Queued",
  running: "Running",
  needs_review: "Needs review",
  completed: "Completed",
  failed: "Failed",
  skipped: "Skipped",
};

export const RUN_LABEL: Record<RunStatus, string> = {
  queued: "Queued",
  running: "Running",
  needs_review: "Needs review",
  completed: "Completed",
  failed: "Failed",
  rejected: "Rejected",
};

export function duration(start: number | null, end: number | null, now = Date.now() / 1000): string {
  if (!start) return "";
  const s = Math.max(0, (end ?? now) - start);
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${Math.round(s % 60)}s`;
}

export function clock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function relative(ts: number, now = Date.now() / 1000): string {
  const s = Math.max(0, now - ts);
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(ts * 1000).toLocaleDateString();
}
