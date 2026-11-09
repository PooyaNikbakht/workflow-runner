import type { ButtonHTMLAttributes, ReactNode } from "react";
import { IconCheck, IconRetry, IconUser, IconX } from "@/components/icons";
import { RUN_LABEL, STEP_LABEL } from "@/lib/format";
import type { RunStatus, StepStatus } from "@/lib/types";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-accent-ink border-accent hover:opacity-90",
  secondary: "bg-background text-ink border-line-strong hover:bg-surface",
  ghost: "bg-transparent text-ink border-transparent hover:bg-surface",
  danger: "bg-background text-danger border-line-strong hover:bg-danger-soft",
};

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" }) {
  return (
    <button
      type="button"
      className={cx(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg border font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "h-9 px-3 text-sm" : "h-11 px-4 text-sm",
        VARIANTS[variant],
        className,
      )}
      {...rest}
    />
  );
}

type AnyStatus = StepStatus | RunStatus;

const STYLE: Record<AnyStatus, string> = {
  pending: "bg-background text-muted border-line",
  queued: "bg-surface text-muted border-line",
  running: "bg-accent-soft text-accent border-accent/40",
  needs_review: "bg-amber-soft text-amber border-amber/40",
  completed: "bg-accent text-accent-ink border-accent",
  failed: "bg-danger-soft text-danger border-danger/40",
  skipped: "bg-background text-muted border-line",
  rejected: "bg-danger-soft text-danger border-danger/40",
};

export function StatusPill({ status, kind = "step" }: { status: AnyStatus; kind?: "step" | "run" }) {
  const label =
    kind === "run" ? RUN_LABEL[status as RunStatus] : STEP_LABEL[status as StepStatus];
  return (
    <span
      className={cx(
        "inline-flex h-6 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 text-xs font-medium",
        STYLE[status],
      )}
    >
      {(status === "running" || status === "queued") && (
        <span
          className={cx(
            "h-1.5 w-1.5 rounded-full bg-current",
            status === "running" && "animate-pulse-soft",
          )}
        />
      )}
      {status === "completed" && <IconCheck size={12} />}
      {status === "needs_review" && <IconUser size={12} />}
      {(status === "failed" || status === "rejected") && <IconX size={12} />}
      {label}
    </span>
  );
}

/** The round marker on the stepper rail. */
export function StepMarker({ status, retrying }: { status: StepStatus; retrying?: boolean }) {
  const base = "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border";
  if (retrying)
    return (
      <span className={cx(base, "border-amber bg-amber-soft text-amber")}>
        <IconRetry size={15} />
      </span>
    );
  switch (status) {
    case "completed":
      return (
        <span className={cx(base, "border-accent bg-accent text-accent-ink")}>
          <IconCheck size={15} />
        </span>
      );
    case "running":
      return (
        <span className={cx(base, "border-accent bg-accent-soft text-accent")}>
          <Spinner size={15} />
        </span>
      );
    case "needs_review":
      return (
        <span className={cx(base, "border-amber bg-amber-soft text-amber")}>
          <IconUser size={15} />
        </span>
      );
    case "failed":
      return (
        <span className={cx(base, "border-danger bg-danger-soft text-danger")}>
          <IconX size={15} />
        </span>
      );
    case "queued":
      return (
        <span className={cx(base, "border-line-strong bg-surface text-muted")}>
          <span className="h-2 w-2 animate-pulse-soft rounded-full bg-current" />
        </span>
      );
    default:
      return (
        <span className={cx(base, "border-line bg-background text-muted")}>
          <span className="h-1.5 w-1.5 rounded-full bg-current opacity-60" />
        </span>
      );
  }
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cx("rounded-lg border border-line bg-background", className)}>{children}</div>;
}

export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" className="animate-spin" aria-hidden="true">
      <circle cx="10" cy="10" r="7.5" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      <path d="M17.5 10a7.5 7.5 0 0 0-7.5-7.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function Notice({
  tone = "neutral",
  children,
  className,
}: {
  tone?: "neutral" | "warn" | "error" | "success";
  children: ReactNode;
  className?: string;
}) {
  const style = {
    neutral: "border-line bg-surface text-ink",
    warn: "border-amber/40 bg-amber-soft text-ink",
    error: "border-danger/40 bg-danger-soft text-ink",
    success: "border-accent/40 bg-accent-soft text-ink",
  }[tone];
  return <div className={cx("rounded-lg border px-4 py-3 text-sm", style, className)}>{children}</div>;
}

export function DemoBadge() {
  return (
    <span
      title="No API key is set, so a deterministic offline model answers the AI steps."
      className="inline-flex h-6 items-center rounded-full border border-line px-2.5 font-mono text-[11px] text-muted"
    >
      demo mode
    </span>
  );
}
