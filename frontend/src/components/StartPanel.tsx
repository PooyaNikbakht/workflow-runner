"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { IconArrowRight } from "@/components/icons";
import { Button, Card, Notice, Spinner, cx } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { Json, Workflow } from "@/lib/types";

type Field =
  | { name: string; label: string; type: "text" | "email"; hint?: string; autoComplete?: string }
  | { name: string; label: string; type: "textarea"; hint?: string; rows: number }
  | { name: string; label: string; type: "select"; options: string[]; hint?: string }
  | { name: string; label: string; type: "checkbox"; hint?: string };

const FIELDS: Record<string, Field[]> = {
  lead_outreach: [
    { name: "name", label: "Name", type: "text", autoComplete: "off" },
    { name: "email", label: "Email", type: "email", autoComplete: "off" },
    { name: "role", label: "Role", type: "text" },
    {
      name: "company_domain",
      label: "Company domain",
      type: "text",
      hint: "Looked up in a local dataset. Try harborline-freight.example or ledgerleaf.example.",
    },
    { name: "note", label: "Note from the lead", type: "textarea", rows: 2 },
    {
      name: "simulate_transient_failure",
      label: "Simulate a flaky company source",
      type: "checkbox",
      hint: "The first lookup times out, so you can watch the retry with backoff.",
    },
  ],
  ticket_triage: [
    { name: "customer_name", label: "Customer name", type: "text", autoComplete: "off" },
    { name: "email", label: "Email", type: "email", autoComplete: "off" },
    { name: "plan", label: "Plan", type: "select", options: ["free", "team", "business"] },
    { name: "subject", label: "Subject", type: "text" },
    { name: "message", label: "Message", type: "textarea", rows: 4 },
  ],
};

const inputClass =
  "w-full rounded-lg border border-line-strong bg-background px-3 text-sm text-ink placeholder:text-muted focus-visible:border-accent";

export function StartPanel() {
  const router = useRouter();
  const [workflows, setWorkflows] = useState<Workflow[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState("lead_outreach");
  const [sampleIndex, setSampleIndex] = useState(0);
  const [values, setValues] = useState<Json>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    api.workflows().then(
      (list) => {
        setWorkflows(list);
        const first = list.find((w) => w.key === "lead_outreach") ?? list[0];
        if (first) {
          setSelected(first.key);
          setValues({ ...(first.samples[0]?.input ?? {}) });
        }
      },
      (e: Error) => setLoadError(e.message),
    );
  }, []);

  const workflow = workflows?.find((w) => w.key === selected);

  function choose(key: string) {
    const wf = workflows?.find((w) => w.key === key);
    setSelected(key);
    setSampleIndex(0);
    setValues({ ...(wf?.samples[0]?.input ?? {}) });
    setFieldErrors({});
    setError(null);
  }

  function pickSample(index: number) {
    setSampleIndex(index);
    setValues({ ...(workflow?.samples[index]?.input ?? {}) });
    setFieldErrors({});
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setFieldErrors({});
    try {
      const { id } = await api.startRun(selected, values);
      router.push(`/runs/${id}`);
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.message);
      setFieldErrors(Object.fromEntries((apiErr.fields ?? []).map((f) => [f.field, f.message])));
      setSubmitting(false);
    }
  }

  if (loadError) {
    return (
      <Notice tone="error">
        <p className="font-medium">Couldn&apos;t load workflows.</p>
        <p className="mt-1 text-muted">{loadError} Start everything with <code className="font-mono">make dev</code>.</p>
      </Notice>
    );
  }
  if (!workflows || !workflow) {
    return (
      <Card className="flex items-center gap-2 p-6 text-sm text-muted" aria-busy="true">
        <Spinner /> Loading workflows
      </Card>
    );
  }

  return (
    <Card className="p-4 sm:p-6">
      <form onSubmit={submit} noValidate>
        <fieldset>
          <legend className="text-sm font-medium">Workflow</legend>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {workflows.map((wf) => (
              <label
                key={wf.key}
                className={cx(
                  "relative flex cursor-pointer flex-col gap-1 rounded-lg border p-3 has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent",
                  selected === wf.key ? "border-accent bg-accent-soft" : "border-line hover:bg-surface",
                )}
              >
                <input
                  type="radio"
                  name="workflow"
                  value={wf.key}
                  checked={selected === wf.key}
                  onChange={() => choose(wf.key)}
                  className="sr-only"
                />
                <span className="text-sm font-semibold">{wf.name}</span>
                <span className="text-sm text-muted">{wf.description}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <ol aria-label="Steps in this workflow" className="mt-4 flex flex-wrap items-center gap-x-1.5 gap-y-2 text-xs">
          {workflow.steps.map((s, i) => (
            <li key={s.key} className="flex items-center gap-1.5">
              <span
                className={cx(
                  "rounded-full border px-2 py-0.5",
                  s.kind === "llm" && "border-accent/40 text-accent",
                  s.kind === "review" && "border-amber/40 text-amber",
                  (s.kind === "action" || s.kind === "webhook") && "border-line text-muted",
                )}
              >
                {s.title}
                {s.kind === "llm" && <span className="sr-only"> (AI step)</span>}
              </span>
              {i < workflow.steps.length - 1 && <IconArrowRight size={12} className="text-muted" />}
            </li>
          ))}
        </ol>

        <div className="mt-6 border-t border-line pt-5">
          <label htmlFor="sample" className="text-sm font-medium">
            Start from a sample
          </label>
          <select
            id="sample"
            value={sampleIndex}
            onChange={(e) => pickSample(Number(e.target.value))}
            className={cx(inputClass, "mt-1.5 h-11")}
          >
            {workflow.samples.map((s, i) => (
              <option key={s.label} value={i}>
                {s.label}
              </option>
            ))}
          </select>
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {FIELDS[selected]?.map((f) => (
            <FieldInput
              key={f.name}
              field={f}
              value={values[f.name]}
              error={fieldErrors[f.name]}
              onChange={(v) => setValues((prev) => ({ ...prev, [f.name]: v }))}
            />
          ))}
        </div>

        {error && (
          <Notice tone="error" className="mt-4">
            <p role="alert">{error}</p>
          </Notice>
        )}

        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-muted">
            The API queues the first step and returns right away. A worker process runs the steps.
          </p>
          <Button type="submit" variant="primary" disabled={submitting} className="w-full sm:w-auto">
            {submitting ? <Spinner /> : null}
            Start run
          </Button>
        </div>
      </form>
    </Card>
  );
}

function FieldInput({
  field,
  value,
  error,
  onChange,
}: {
  field: Field;
  value: unknown;
  error?: string;
  onChange: (v: unknown) => void;
}) {
  const id = `field-${field.name}`;
  const hintId = "hint" in field && field.hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  if (field.type === "checkbox") {
    return (
      <div className="sm:col-span-2">
        <label htmlFor={id} className="flex min-h-11 cursor-pointer items-start gap-3">
          <input
            id={id}
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
            aria-describedby={describedBy}
            className="mt-0.5 h-5 w-5 shrink-0 accent-[var(--accent)]"
          />
          <span>
            <span className="text-sm font-medium">{field.label}</span>
            {hintId && (
              <span id={hintId} className="block text-sm text-muted">
                {field.hint}
              </span>
            )}
          </span>
        </label>
      </div>
    );
  }

  const wide = field.type === "textarea" || field.name === "company_domain" || field.name === "subject";
  return (
    <div className={cx(wide && "sm:col-span-2")}>
      <label htmlFor={id} className="text-sm font-medium">
        {field.label}
      </label>
      {field.type === "textarea" ? (
        <textarea
          id={id}
          rows={field.rows}
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
          aria-describedby={describedBy}
          aria-invalid={Boolean(error)}
          className={cx(inputClass, "mt-1.5 py-2.5 leading-relaxed")}
        />
      ) : field.type === "select" ? (
        <select
          id={id}
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
          className={cx(inputClass, "mt-1.5 h-11 capitalize")}
        >
          {field.options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          type={field.type}
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={field.autoComplete}
          aria-describedby={describedBy}
          aria-invalid={Boolean(error)}
          className={cx(inputClass, "mt-1.5 h-11", error && "border-danger")}
        />
      )}
      {hintId && (
        <p id={hintId} className="mt-1 text-xs text-muted">
          {field.hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="mt-1 text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
