"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card, Notice, Spinner, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import { relative } from "@/lib/format";
import type { RunSummary } from "@/lib/types";

export function RunHistory() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api.runs().then(
        (r) => {
          if (!alive) return;
          setRuns(r);
          setError(null);
        },
        (e: Error) => alive && setError(e.message),
      );
    load();
    const timer = setInterval(load, 3000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  return (
    <section aria-labelledby="history-heading" className="mt-12">
      <div className="flex items-baseline justify-between gap-4">
        <h2 id="history-heading" className="text-lg font-semibold tracking-tight">
          Run history
        </h2>
        <p className="text-xs text-muted">Stored in SQLite. Refreshes every few seconds.</p>
      </div>

      {error && !runs && (
        <Notice tone="error" className="mt-4">
          Couldn&apos;t load runs. {error}
        </Notice>
      )}
      {!runs && !error && (
        <Card className="mt-4 flex items-center gap-2 p-6 text-sm text-muted" aria-busy="true">
          <Spinner /> Loading runs
        </Card>
      )}
      {runs && runs.length === 0 && (
        <Card className="mt-4 p-6 text-sm text-muted">No runs yet. Start one above and it shows up here.</Card>
      )}
      {runs && runs.length > 0 && (
        <Card className="mt-4 overflow-hidden">
          <ul className="divide-y divide-line">
            {runs.map((r) => (
              <li key={r.id}>
                <Link
                  href={`/runs/${r.id}`}
                  className="flex flex-col gap-2 px-4 py-3 hover:bg-surface focus-visible:rounded-none sm:flex-row sm:items-center sm:gap-4"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{r.title}</span>
                    <span className="block text-xs text-muted">
                      {r.workflow_name} · <span className="font-mono">{r.id}</span>
                    </span>
                  </span>
                  <span className="flex items-center gap-3 text-xs text-muted">
                    <span className="tabular">
                      {r.steps_done}/{r.steps_total} steps
                    </span>
                    {r.retries > 0 && (
                      <span className="tabular">
                        {r.retries} {r.retries === 1 ? "retry" : "retries"}
                      </span>
                    )}
                    <span className="w-20 text-right sm:w-24">{relative(r.created_at)}</span>
                    <StatusPill status={r.status} kind="run" />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </section>
  );
}
