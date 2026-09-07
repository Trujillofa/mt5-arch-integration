"use client";

import { useEffect, useRef } from "react";

/** Slow enough that seven cards do not hammer Wine. File-bridge only on poll. */
export const LIVE_PROBE_POLL_MS = 8000;

export function useLiveProbePoll(
  runPoll: () => Promise<void>,
  busy: boolean
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
    }, LIVE_PROBE_POLL_MS);
    return () => window.clearInterval(id);
  }, []);
}
