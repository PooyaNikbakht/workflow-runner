"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { LogEvent, Run } from "@/lib/types";

export type StreamState = "connecting" | "live" | "reconnecting" | "ended";

/**
 * Loads a run, then follows it over Server-Sent Events.
 *
 * The server sends a `run` snapshot on connect and after every state change, a `log` event per
 * log line (with an id, so the browser resumes with Last-Event-ID after a drop) and `end` once the
 * run is finished.
 */
export function useRunStream(id: string) {
  const [run, setRun] = useState<Run | null>(null);
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [stream, setStream] = useState<StreamState>("connecting");
  const [error, setError] = useState<{ status: number; message: string } | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const seen = useRef(new Set<number>());

  useEffect(() => {
    let source: EventSource | null = null;
    let cancelled = false;

    api.run(id).then(
      (initial) => {
        if (cancelled) return;
        setRun(initial);
        source = new EventSource(api.eventsUrl(id));
        source.onopen = () => setStream("live");
        source.onerror = () => {
          if (source?.readyState === EventSource.CLOSED) setStream("ended");
          else setStream("reconnecting");
        };
        source.addEventListener("run", (e) => setRun(JSON.parse((e as MessageEvent).data)));
        source.addEventListener("log", (e) => {
          const ev: LogEvent = JSON.parse((e as MessageEvent).data);
          if (seen.current.has(ev.id)) return;
          seen.current.add(ev.id);
          setLogs((prev) => [...prev, ev]);
          if (ev.kind === "state") setAnnouncement(ev.message);
        });
        source.addEventListener("end", () => {
          setStream("ended");
          source?.close();
        });
      },
      (err: ApiError) => {
        if (!cancelled) setError({ status: err.status, message: err.message });
      },
    );

    return () => {
      cancelled = true;
      source?.close();
    };
  }, [id]);

  return { run, logs, stream, error, announcement };
}

/** A clock that ticks while `active`, for running durations and retry countdowns. */
export function useNow(active: boolean, interval = 500): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now() / 1000), interval);
    return () => clearInterval(timer);
  }, [active, interval]);
  return now;
}
