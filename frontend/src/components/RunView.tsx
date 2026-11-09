"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { LogPanel } from "@/components/LogPanel";
import { ReviewDrawer } from "@/components/ReviewDrawer";
import { Stepper } from "@/components/Stepper";
import { IconInbox, IconUser } from "@/components/icons";
import { Button, Card, Notice, Spinner, StatusPill } from "@/components/ui";
import { duration, relative } from "@/lib/format";
import { useNow, useRunStream } from "@/lib/useRunStream";

export function RunView({ id }: { id: string }) {
  const { run, logs, stream, error, announcement } = useRunStream(id);
  const [reviewOpen, setReviewOpen] = useState(false);
  const closeReview = useCallback(() => setReviewOpen(false), []);
  const active = run ? !["completed", "failed", "rejected"].includes(run.status) : false;
  const now = useNow(active);

  if (error) {
    return (
      <Shell>
        <Notice tone="error">
          <p className="font-medium">{error.status === 404 ? "Run not found." : "Couldn't load this run."}</p>
          <p className="mt-1 text-muted">{error.status === 404 ? "It may have been created on another machine." : error.message}</p>
        </Notice>
      </Shell>
    );
  }
  if (!run) {
    return (
      <Shell>
        <Card className="flex items-center gap-2 p-6 text-sm text-muted" aria-busy="true">
          <Spinner /> Loading run
        </Card>
      </Shell>
    );
  }

  const send = run.steps.find((s) => s.key === "send");
  const done = run.steps.filter((s) => s.status === "completed").length;

  return (
    <Shell>
      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {announcement}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm text-muted">{run.workflow_name}</p>
          <h1 className="mt-1 break-words text-xl font-semibold tracking-tight sm:text-2xl">{run.title}</h1>
          <p className="mt-1.5 text-xs text-muted">
            <span className="font-mono">{run.id}</span> · started {relative(run.created_at, now)} ·{" "}
            <span className="tabular">{duration(run.created_at, run.finished_at, now)}</span> ·{" "}
            <span className="tabular">
              {done} of {run.steps.length} steps done
            </span>
          </p>
        </div>
        <span className="self-start">
          <StatusPill status={run.status} kind="run" />
        </span>
      </div>

      <div className="mt-5 space-y-3">
        {run.status === "needs_review" && (
          <Notice tone="warn" className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="flex items-center gap-2">
              <IconUser size={16} className="shrink-0 text-amber" />
              <span>
                <span className="font-medium">The draft is ready for review.</span> The run is paused until
                you decide.
              </span>
            </p>
            <Button variant="primary" size="sm" onClick={() => setReviewOpen(true)}>
              Open review
            </Button>
          </Notice>
        )}
        {run.status === "completed" && send?.output && (
          <Notice tone="success" className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p>
              <span className="font-medium">Delivered.</span> The receiver answered{" "}
              {String(send.output.status_code)} with idempotency key{" "}
              <span className="break-all font-mono text-xs">{String(send.output.idempotency_key)}</span>.
            </p>
            <Link
              href="/receiver"
              className="inline-flex h-9 shrink-0 items-center gap-2 rounded-lg border border-line-strong bg-background px-3 text-sm font-medium hover:bg-surface"
            >
              <IconInbox size={15} /> See payload
            </Link>
          </Notice>
        )}
        {run.status === "failed" && (
          <Notice tone="error">
            <span className="font-medium">Run failed.</span> {run.error}
          </Notice>
        )}
        {run.status === "rejected" && (
          <Notice tone="neutral">
            <span className="font-medium">Rejected at review.</span> Nothing was sent.
          </Notice>
        )}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <section aria-labelledby="steps-heading" className="min-w-0">
          <h2 id="steps-heading" className="sr-only">
            Steps
          </h2>
          <Card className="p-4 sm:p-5">
            <Stepper steps={run.steps} now={now} />
          </Card>
        </section>
        <section aria-label="Log" className="min-w-0 lg:sticky lg:top-6 lg:self-start">
          <LogPanel logs={logs} stream={stream} />
        </section>
      </div>

      {reviewOpen && run.status === "needs_review" && <ReviewDrawer run={run} onClose={closeReview} />}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
      <Link href="/" className="rounded text-sm text-muted hover:text-ink">
        ← All runs
      </Link>
      <div className="mt-4">{children}</div>
    </div>
  );
}
