import type { Json, Step } from "@/lib/types";
import { cx } from "@/components/ui";

type Obj = Record<string, unknown>;
const o = (v: unknown) => (v ?? {}) as Obj;
const s = (v: unknown) => (v == null ? "" : String(v));

/** One line that says what a finished step produced. */
export function stepSummary(step: Step): string {
  const out = step.output;
  if (!out) return "";
  switch (step.key) {
    case "intake": {
      const lead = o(out.lead);
      const ticket = o(out.ticket);
      return lead.name ? `${s(lead.name)}, ${s(lead.company_domain)}` : `${s(ticket.customer_name)}, ${s(ticket.plan)} plan`;
    }
    case "fetch_company": {
      const c = o(out.company);
      return `${s(c.name)}, ${s(c.industry)}, ${(c.signals as unknown[])?.length ?? 0} signals`;
    }
    case "pain_points":
      return `${(out.pain_points as unknown[]).length} pain points found`;
    case "draft_email":
    case "suggest_reply":
      return `Subject: ${s(out.subject)}`;
    case "classify":
      return `${s(out.category).replace("_", " ")}, ${s(out.priority)} priority, ${s(out.sentiment)}`;
    case "review":
      if (step.status === "needs_review") return "Waiting for a decision";
      if (out.decision === "reject") return "Rejected";
      return out.edited ? "Approved with edits" : "Approved as written";
    case "send":
      return `Receiver answered ${s(out.status_code)} (${s(o(out.receiver).status)})`;
    default:
      return "";
  }
}

function Email({ subject, body }: { subject: unknown; body: unknown }) {
  return (
    <div className="rounded-lg border border-line bg-background">
      <p className="border-b border-line px-3 py-2 text-sm font-medium">{s(subject)}</p>
      <p className="whitespace-pre-wrap px-3 py-2.5 text-sm leading-relaxed">{s(body)}</p>
    </div>
  );
}

function Pairs({ rows }: { rows: [string, unknown][] }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
      {rows
        .filter(([, v]) => v !== "" && v != null)
        .map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted">{k}</dt>
            <dd className="min-w-0 break-words">{s(v)}</dd>
          </div>
        ))}
    </dl>
  );
}

const IMPACT = {
  high: "border-danger/40 text-danger",
  medium: "border-amber/40 text-amber",
  low: "border-line text-muted",
} as Record<string, string>;

export function StepOutput({ step }: { step: Step }) {
  const out = step.output as Json;
  switch (step.key) {
    case "intake": {
      const lead = o(out.lead);
      if (lead.name)
        return (
          <Pairs
            rows={[
              ["Name", lead.name],
              ["Email", lead.email],
              ["Role", lead.role],
              ["Domain", lead.company_domain],
              ["Note", lead.note],
            ]}
          />
        );
      const t = o(out.ticket);
      return (
        <div className="space-y-2">
          <Pairs rows={[["From", `${s(t.customer_name)} <${s(t.email)}>`], ["Plan", t.plan], ["Subject", t.subject]]} />
          <p className="whitespace-pre-wrap rounded-lg bg-surface px-3 py-2 text-sm">{s(t.message)}</p>
        </div>
      );
    }
    case "fetch_company": {
      const c = o(out.company);
      return (
        <div className="space-y-3">
          <Pairs rows={[["Company", c.name], ["Industry", c.industry], ["Size", c.size], ["Location", c.location]]} />
          <ul className="space-y-1.5 text-sm">
            {(c.signals as Obj[]).map((sig, i) => (
              <li key={i} className="flex gap-2">
                <span className="mt-0.5 shrink-0 rounded border border-line px-1.5 font-mono text-[11px] text-muted">
                  {s(sig.source)}
                </span>
                <span>{s(sig.text)}</span>
              </li>
            ))}
          </ul>
        </div>
      );
    }
    case "pain_points":
      return (
        <div className="space-y-3">
          <p className="text-sm">{s(out.summary)}</p>
          <ul className="space-y-2">
            {(out.pain_points as Obj[]).map((p, i) => (
              <li key={i} className="rounded-lg border border-line px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{s(p.title)}</span>
                  <span className={cx("rounded-full border px-2 text-[11px]", IMPACT[s(p.impact)])}>
                    {s(p.impact)} impact
                  </span>
                </div>
                <p className="mt-1 text-sm text-muted">{s(p.evidence)}</p>
              </li>
            ))}
          </ul>
        </div>
      );
    case "draft_email":
    case "suggest_reply":
      return (
        <div className="space-y-2">
          <Email subject={out.subject} body={out.body} />
          {out.internal_note ? <p className="text-sm text-muted">Internal note: {s(out.internal_note)}</p> : null}
        </div>
      );
    case "classify":
      return (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2 font-mono text-xs">
            {["category", "priority", "sentiment"].map((k) => (
              <span key={k} className="rounded border border-line px-2 py-0.5">
                {k}: {s(out[k])}
              </span>
            ))}
            <span className="rounded border border-line px-2 py-0.5">
              confidence: {Math.round(Number(out.confidence) * 100)}%
            </span>
          </div>
          <p className="text-sm">{s(out.summary)}</p>
        </div>
      );
    case "review": {
      if (step.status === "needs_review") return <p className="text-sm text-muted">Open the review panel to decide.</p>;
      const final = o(out.final);
      return (
        <div className="space-y-2">
          <Pairs rows={[["Decision", out.decision], ["Edited", out.edited ? "yes" : out.decision === "reject" ? "" : "no"], ["Note", out.note]]} />
          {final.subject ? <Email subject={final.subject} body={final.body} /> : null}
        </div>
      );
    }
    case "send":
      return (
        <Pairs
          rows={[
            ["Event", out.event],
            ["Endpoint", out.url],
            ["Status", out.status_code],
            ["Receiver", o(out.receiver).status],
            ["Idempotency key", out.idempotency_key],
          ]}
        />
      );
    default:
      return <pre className="overflow-x-auto rounded-lg bg-surface p-3 font-mono text-xs">{JSON.stringify(out, null, 2)}</pre>;
  }
}
