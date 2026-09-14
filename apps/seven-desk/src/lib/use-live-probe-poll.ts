"use client";

import { useEffect, useRef } from "react";

/** Slow enough that seven cards do not hammer Wine. File-bridge only on poll. */
export const LIVE_PROBE_POLL_MS = 8000;
/** FTMO terminal follow only. Other firm cards stay at 8s. */
export const LIVE_FOLLOW_POLL_MS = 2000;

export function useLiveProbePoll(
  runPoll: () => Promise<void>,
  busy: boolean,
  intervalMs: number = LIVE_PROBE_POLL_MS
): void {
  const busyRef = useRef(busy);
  const runRef = useRef(runPoll);

  useEffect(() => {
    busyRef.current = busy;
    runRef.current = runPoll;
  }, [busy, runPoll]);

  useEffect(() => {
    const id = window.setInterval(() => {
      if (busyRef.current) return;
      void runRef.current();
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
}
