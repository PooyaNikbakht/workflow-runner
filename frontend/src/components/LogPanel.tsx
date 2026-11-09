"use client";

import { useEffect, useRef, useState } from "react";
import { Card, cx } from "@/components/ui";
import { clock } from "@/lib/format";
import type { LogEvent } from "@/lib/types";
import type { StreamState } from "@/lib/useRunStream";

const LEVEL_STYLE: Record<LogEvent["level"], string> = {
  debug: "text-muted",
  info: "text-ink",
  warn: "text-amber",
  error: "text-danger",
};

const STREAM_LABEL: Record<StreamState, string> = {
  connecting: "Connecting",
  live: "Live",
  reconnecting: "Reconnecting",
  ended: "Run finished",
};

export function LogPanel({ logs, stream }: { logs: LogEvent[]; stream: StreamState }) {
  const [showDebug, setShowDebug] = useState(true);
  const box = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const visible = showDebug ? logs : logs.filter((l) => l.level !== "debug");

  // Follow new lines unless the reader scrolled up.
  useEffect(() => {
    const el = box.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [visible.length]);

  return (
    <Card className="flex flex-col overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
        <h2 className="text-sm font-semibold">Live log</h2>
        <div className="flex items-center gap-3 text-xs text-muted">
          <label className="flex cursor-pointer items-center gap-1.5">
            <input
              type="checkbox"
              checked={showDebug}
              onChange={(e) => setShowDebug(e.target.checked)}
              className="h-4 w-4 accent-[var(--accent)]"
            />
            Debug lines
          </label>
          <span className="inline-flex items-center gap-1.5" title="Server-Sent Events connection">
            <span
              aria-hidden="true"
              className={cx(
                "h-2 w-2 rounded-full",
                stream === "live" && "animate-pulse-soft bg-accent",
                stream === "ended" && "bg-muted",
                (stream === "connecting" || stream === "reconnecting") && "bg-amber",
              )}
            />
            {STREAM_LABEL[stream]}
          </span>
        </div>
      </div>
      <div
        ref={box}
        tabIndex={0}
        role="log"
        aria-label="Run log"
        aria-live="off"
        onScroll={(e) => {
          const el = e.currentTarget;
          pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
        className="h-80 overflow-y-auto px-4 py-3 font-mono text-xs leading-relaxed lg:h-[34rem]"
      >
        {visible.length === 0 ? (
          <p className="text-muted">Waiting for the worker to pick up the first step.</p>
        ) : (
          <ol className="space-y-1">
            {visible.map((l) => (
              <li key={l.id} className="grid grid-cols-[auto_1fr] gap-x-3">
                <time className="tabular text-muted" dateTime={new Date(l.ts * 1000).toISOString()}>
                  {clock(l.ts)}
                </time>
                <span className={cx("min-w-0 break-words", LEVEL_STYLE[l.level], l.kind === "state" && "font-semibold")}>
                  {l.step && <span className="mr-1.5 font-normal text-muted">[{l.step}]</span>}
                  {l.level === "warn" && <span className="sr-only">Warning: </span>}
                  {l.level === "error" && <span className="sr-only">Error: </span>}
                  {l.message}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </Card>
  );
}
