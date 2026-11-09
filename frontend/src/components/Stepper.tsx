"use client";

import { useState } from "react";
import { StepOutput, stepSummary } from "@/components/StepOutput";
import { IconChevron } from "@/components/icons";
import { StatusPill, StepMarker, cx } from "@/components/ui";
import { duration } from "@/lib/format";
import type { Step } from "@/lib/types";

const KIND_LABEL = { action: "action", llm: "AI", review: "human", webhook: "webhook" } as const;

export function Stepper({ steps, now }: { steps: Step[]; now: number }) {
  return (
    <ol className="relative" aria-label="Workflow steps">
      {steps.map((step, i) => (
        <StepItem key={step.key} step={step} last={i === steps.length - 1} now={now} />
      ))}
    </ol>
  );
}

function StepItem({ step, last, now }: { step: Step; last: boolean; now: number }) {
  const [open, setOpen] = useState(false);
  const retryIn = step.status === "queued" && step.next_attempt_at ? step.next_attempt_at - now : null;
  const retrying = step.status === "queued" && step.attempts > 0;
  const summary = stepSummary(step);
  const hasOutput = Boolean(step.output);
  const panelId = `step-${step.key}-output`;

  return (
    <li className="relative flex gap-3 pb-6 last:pb-0">
      {!last && (
        <span
          aria-hidden="true"
          className={cx(
            "absolute left-4 top-9 bottom-1 w-px -translate-x-1/2",
            step.status === "completed" ? "bg-accent" : "bg-line",
          )}
        />
      )}
      <StepMarker status={step.status} retrying={retrying} />
      <div className="min-w-0 flex-1 pt-0.5">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <h3 className={cx("text-sm font-semibold", step.status === "skipped" && "text-muted line-through")}>
            {step.title}
          </h3>
          <span className="rounded border border-line px-1.5 font-mono text-[10px] uppercase tracking-wide text-muted">
            {KIND_LABEL[step.kind]}
          </span>
          <span className="ml-auto">
            <StatusPill status={step.status} />
          </span>
        </div>
        <p className="mt-0.5 text-xs text-muted">
          {step.attempts > 0 && (
            <span className="tabular">
              Attempt {step.attempts} of {step.max_attempts}
              {step.started_at ? ` · ${duration(step.started_at, step.finished_at, now)}` : ""}
            </span>
          )}
          {step.attempts === 0 && step.description}
        </p>

        {retrying && (
          <p className="mt-2 rounded-lg border border-amber/40 bg-amber-soft px-3 py-2 text-xs">
            <span className="font-medium">{step.error}</span>{" "}
            {retryIn !== null && retryIn > 0 ? (
              <span className="tabular">Retrying in {retryIn.toFixed(1)}s with backoff.</span>
            ) : (
              <span>Retrying now.</span>
            )}
          </p>
        )}
        {step.status === "failed" && step.error && (
          <p className="mt-2 rounded-lg border border-danger/40 bg-danger-soft px-3 py-2 text-xs">{step.error}</p>
        )}
        {step.status === "completed" && step.attempts > 1 && (
          <p className="mt-1 text-xs text-amber">
            Succeeded after {step.attempts - 1} {step.attempts === 2 ? "retry" : "retries"}.
          </p>
        )}

        {hasOutput && (
          <div className="mt-2">
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              aria-expanded={open}
              aria-controls={panelId}
              className="flex w-full items-center gap-2 rounded-lg border border-line px-3 py-2 text-left text-sm hover:bg-surface"
            >
              <span className="min-w-0 flex-1 truncate">{summary || "Output"}</span>
              <IconChevron size={14} className={cx("shrink-0 text-muted transition-transform", open && "rotate-180")} />
            </button>
            {open && (
              <div id={panelId} className="mt-2 rounded-lg border border-line bg-surface/50 p-3">
                <StepOutput step={step} />
              </div>
            )}
          </div>
        )}
      </div>
    </li>
  );
}
