"use client";

import { useEffect, useState } from "react";
import { useConfig } from "@/components/ConfigProvider";
import { IconCheck, IconX } from "@/components/icons";
import { Card, Notice, Spinner, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { clock, relative } from "@/lib/format";
import type { Delivery } from "@/lib/types";

export function ReceiverView() {
  const config = useConfig();
  const [items, setItems] = useState<Delivery[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api.deliveries().then(
        (d) => {
          if (!alive) return;
          setItems(d);
          setError(null);
        },
        (e: Error) => alive && setError(e.message),
      );
    load();
    const timer = setInterval(load, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-10 sm:px-6 sm:py-14">
      <h1 className="text-2xl font-semibold tracking-tight">Mock webhook receiver</h1>
      <p className="mt-3 max-w-2xl text-muted">
        Stands in for the system on the other end, like a CRM or a help desk. It checks the HMAC signature
        and stores each delivery once per idempotency key, so a retried send never shows up twice.
      </p>
      {config && (
        <p className="mt-3 break-all font-mono text-xs text-muted">POST {config.webhook_url}</p>
      )}

      <div className="mt-8 space-y-4" aria-live="polite" aria-busy={!items && !error}>
        {error && !items && <Notice tone="error">Couldn&apos;t load deliveries. {error}</Notice>}
        {!items && !error && (
          <Card className="flex items-center gap-2 p-6 text-sm text-muted">
            <Spinner /> Loading deliveries
          </Card>
        )}
        {items && items.length === 0 && (
          <Card className="p-6 text-sm text-muted">
            Nothing received yet. Approve a run at its review step and the send step posts here.
          </Card>
        )}
        {items?.map((d) => <DeliveryCard key={d.id} d={d} />)}
      </div>
    </div>
  );
}

function DeliveryCard({ d }: { d: Delivery }) {
  const data = d.payload.data ?? {};
  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-line px-4 py-3">
        <span className="font-mono text-xs font-medium">{d.event}</span>
        <span
          className={cx(
            "inline-flex items-center gap-1 rounded-full border px-2 text-[11px]",
            d.signature_ok ? "border-accent/40 text-accent" : "border-danger/40 text-danger",
          )}
        >
          {d.signature_ok ? <IconCheck size={11} /> : <IconX size={11} />}
          {d.signature_ok ? "Signature valid" : "Bad signature"}
        </span>
        {d.attempts > 1 && (
          <span className="rounded-full border border-amber/40 px-2 text-[11px] text-amber">
            {d.attempts - 1} duplicate {d.attempts === 2 ? "delivery" : "deliveries"} dropped
          </span>
        )}
        <span className="ml-auto text-xs text-muted">
          <time dateTime={new Date(d.received_at * 1000).toISOString()}>{clock(d.received_at)}</time> ·{" "}
          {relative(d.received_at)}
        </span>
      </div>
      <div className="space-y-3 px-4 py-4">
        {data.to && (
          <p className="text-sm">
            <span className="text-muted">To </span>
            {data.to.name} &lt;{data.to.email}&gt;
          </p>
        )}
        {data.subject && (
          <div className="rounded-lg border border-line">
            <p className="border-b border-line px-3 py-2 text-sm font-medium">{data.subject}</p>
            <p className="whitespace-pre-wrap px-3 py-2.5 text-sm leading-relaxed">{data.body}</p>
          </div>
        )}
        <details className="group">
          <summary className="cursor-pointer rounded text-sm text-muted hover:text-ink">Raw payload</summary>
          <pre className="mt-2 overflow-x-auto rounded-lg bg-surface p-3 font-mono text-xs leading-relaxed">
            {JSON.stringify(d.payload, null, 2)}
          </pre>
        </details>
        <p className="break-all font-mono text-[11px] text-muted">Idempotency-Key: {d.idempotency_key}</p>
      </div>
    </Card>
  );
}
