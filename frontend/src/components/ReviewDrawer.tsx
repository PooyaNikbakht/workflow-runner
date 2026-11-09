"use client";

import { useEffect, useRef, useState } from "react";
import { IconX } from "@/components/icons";
import { Button, Notice, Spinner, cx } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { Run } from "@/lib/types";

type Proposal = { subject: string; body: string };

const field =
  "w-full rounded-lg border border-line-strong bg-background px-3 text-sm text-ink focus-visible:border-accent";

export function ReviewDrawer({ run, onClose }: { run: Run; onClose: () => void }) {
  const step = run.steps.find((s) => s.status === "needs_review");
  const proposal = (step?.output?.proposal ?? { subject: "", body: "" }) as Proposal;
  const [subject, setSubject] = useState(proposal.subject);
  const [body, setBody] = useState(proposal.body);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const panel = useRef<HTMLDivElement>(null);
  const edited = subject !== proposal.subject || body !== proposal.body;

  // Focus the first field, keep Tab inside the drawer, close on Escape, restore focus on close.
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLElement>("input, textarea, button")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panel.current) return;
      const items = panel.current.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input, textarea, select, [href], [tabindex]:not([tabindex='-1'])",
      );
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      previous?.focus();
    };
  }, [onClose]);

  async function decide(decision: "approve" | "reject") {
    setBusy(decision);
    setError(null);
    try {
      if (decision === "reject") await api.review(run.id, { decision: "reject", note });
      else if (edited) await api.review(run.id, { decision: "edit", edits: { subject, body }, note });
      else await api.review(run.id, { decision: "approve", note });
      onClose();
    } catch (err) {
      const e = err as ApiError;
      setError(e.status === 409 ? "This run was already reviewed. The page will update." : e.message);
      setBusy(null);
    }
  }

  const outputs = Object.fromEntries(run.steps.map((s) => [s.key, s.output ?? {}])) as Record<
    string,
    Record<string, unknown>
  >;
  const lead = outputs.intake?.lead as Record<string, string> | undefined;
  const ticket = outputs.intake?.ticket as Record<string, string> | undefined;
  const to = lead ? `${lead.name} <${lead.email}>` : ticket ? `${ticket.customer_name} <${ticket.email}>` : "";

  return (
    <div className="fixed inset-0 z-40 flex items-end md:items-stretch md:justify-end">
      <div className="absolute inset-0 bg-overlay" onClick={onClose} aria-hidden="true" />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-title"
        aria-describedby="review-desc"
        className="drawer-panel relative flex max-h-[92vh] w-full flex-col rounded-t-xl border border-line bg-background md:h-full md:max-h-none md:w-[34rem] md:rounded-none md:border-y-0 md:border-r-0"
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-4 py-4 sm:px-6">
          <div>
            <h2 id="review-title" className="text-base font-semibold">
              Review before sending
            </h2>
            <p id="review-desc" className="mt-0.5 text-sm text-muted">
              Approve as written, edit and approve, or reject. Nothing is sent until you decide.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="-mr-2 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-surface hover:text-ink"
          >
            <IconX size={18} />
            <span className="sr-only">Close review</span>
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-4 py-5 sm:px-6">
          <section aria-label="Context" className="rounded-lg border border-line bg-surface px-3 py-3 text-sm">
            <p>
              <span className="text-muted">To </span>
              {to}
            </p>
            {outputs.pain_points?.summary ? (
              <p className="mt-1.5 text-muted">{String(outputs.pain_points.summary)}</p>
            ) : null}
            {outputs.classify?.category ? (
              <p className="mt-1.5 font-mono text-xs text-muted">
                {String(outputs.classify.category)} · {String(outputs.classify.priority)} priority ·{" "}
                {String(outputs.classify.sentiment)}
              </p>
            ) : null}
            {ticket?.message ? <p className="mt-2 whitespace-pre-wrap">{ticket.message}</p> : null}
          </section>

          <div>
            <label htmlFor="review-subject" className="text-sm font-medium">
              Subject
            </label>
            <input
              id="review-subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className={cx(field, "mt-1.5 h-11")}
            />
          </div>
          <div>
            <label htmlFor="review-body" className="text-sm font-medium">
              Message
            </label>
            <textarea
              id="review-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={12}
              className={cx(field, "mt-1.5 py-2.5 leading-relaxed")}
            />
            <div className="mt-1 flex items-center justify-between text-xs text-muted">
              <span className="tabular">{body.trim().split(/\s+/).filter(Boolean).length} words</span>
              {edited && (
                <button
                  type="button"
                  onClick={() => {
                    setSubject(proposal.subject);
                    setBody(proposal.body);
                  }}
                  className="rounded underline underline-offset-2 hover:text-ink"
                >
                  Undo my edits
                </button>
              )}
            </div>
          </div>
          <div>
            <label htmlFor="review-note" className="text-sm font-medium">
              Note <span className="font-normal text-muted">(optional, saved to the run log)</span>
            </label>
            <textarea
              id="review-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              className={cx(field, "mt-1.5 py-2")}
            />
          </div>
          {error && (
            <Notice tone="error">
              <p role="alert">{error}</p>
            </Notice>
          )}
        </div>

        <div className="flex flex-col-reverse gap-2 border-t border-line px-4 py-4 sm:flex-row sm:justify-between sm:px-6">
          <Button variant="danger" onClick={() => decide("reject")} disabled={busy !== null}>
            {busy === "reject" && <Spinner />}
            Reject
          </Button>
          <Button
            variant="primary"
            onClick={() => decide("approve")}
            disabled={busy !== null || subject.trim().length < 3 || body.trim().length < 10}
          >
            {busy === "approve" && <Spinner />}
            {edited ? "Save edits and send" : "Approve and send"}
          </Button>
        </div>
      </div>
    </div>
  );
}
