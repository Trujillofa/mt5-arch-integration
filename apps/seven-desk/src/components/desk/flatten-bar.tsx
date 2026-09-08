"use client";

import { Button } from "@/components/ui/button";
import { describeFlattenTargets } from "@/lib/copy-engine";
import { useDesk } from "@/lib/desk-context";

export function FlattenBar() {
  const { state, busy, flattenAll } = useDesk();
  const summary = describeFlattenTargets(state);
  const canFlatten = summary.filled + summary.pending > 0;
  const us30Warn =
    summary.us30Rows.length > 0
      ? `Includes ${summary.us30Rows
          .map((row) => `${row.symbol} ${row.lots.toFixed(1)}`)
          .join(", ")} — flatten will close/cancel those US30/DJ30 desk rows.`
      : null;

  const title = [
    "Closes every desk position (market close) and cancels working limits/stops.",
    "Does not mass-close broker leftovers (including leftover US30/DJ30 4.0s) — close those rows explicitly.",
    us30Warn ?? "No US30/DJ30 desk rows in this flatten.",
  ].join(" ");

  let label = "Close positions";
  if (busy) {
    label = "Closing…";
  } else if (summary.pending > 0) {
    label = "Close positions · cancel pendings";
  }

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 border-t border-rose-500/50 bg-zinc-950/95 pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] backdrop-blur">
      <div className="mx-auto flex w-full flex-col gap-1.5 px-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))]">
        {canFlatten ? (
          us30Warn ? (
            <p className="text-center text-[11px] font-medium text-amber-300">{us30Warn}</p>
          ) : (
            <p className="text-center text-[11px] text-muted-foreground">
              Desk book only · {summary.filled} position{summary.filled === 1 ? "" : "s"}
              {summary.pending
                ? ` · ${summary.pending} working limit${summary.pending === 1 ? "" : "s"}`
                : ""}
              {summary.leftovers
                ? ` · ${summary.leftovers} leftover${summary.leftovers === 1 ? "" : "s"} visible, not flattened`
                : " · leftovers not flattened"}
            </p>
          )
        ) : (
          <p className="text-center text-[11px] font-medium text-amber-300">
            No desk positions or working limits. Leftover US30/DJ30 4.0s can appear
            in Positions — this does not mass-close them.
          </p>
        )}
        <Button
          type="button"
          variant="destructive"
          disabled={busy || !canFlatten}
          title={title}
          aria-label={title}
          className="h-11 min-h-11 w-full bg-rose-600 text-base font-semibold text-white hover:bg-rose-500 disabled:opacity-70 md:text-sm"
          onClick={() => flattenAll()}
        >
          {label}
        </Button>
      </div>
    </div>
  );
}
