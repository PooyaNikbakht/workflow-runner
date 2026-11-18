"use client";

import { useEffect, useRef } from "react";

const MAX_BACKOFF_MS = 30_000;

/**
 * Calls `load` every `intervalMs` while the tab is visible. A hidden tab stops polling and
 * refreshes once when it becomes visible again. After a failed call the wait doubles (up to 30 s)
 * and resets on the next success, so a struggling or rate-limited API gets breathing room.
 */
export function usePolling(load: () => Promise<void>, intervalMs: number) {
  const latest = useRef(load);
  useEffect(() => {
    latest.current = load;
  });

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = intervalMs;

    const tick = async () => {
      timer = undefined;
      try {
        await latest.current();
        delay = intervalMs;
      } catch {
        delay = Math.min(delay * 2, MAX_BACKOFF_MS);
      }
      if (alive && document.visibilityState === "visible") timer = setTimeout(tick, delay);
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        if (timer === undefined) tick();
      } else {
        clearTimeout(timer);
        timer = undefined;
      }
    };

    document.addEventListener("visibilitychange", onVisibility);
    if (document.visibilityState === "visible") tick();
    return () => {
      alive = false;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [intervalMs]);
}
