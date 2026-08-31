import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ConnectionStatus, CopyStatus, Side } from "@/lib/types";

export function ConnectionPill({ status }: { status: ConnectionStatus }) {
  const label =
    status === "connected"
      ? "Connected"
      : status === "connecting"
        ? "Connecting"
        : status === "error"
          ? "Error"
          : "Disconnected";
  return (
    <Badge
      variant="outline"
      className={cn(
        "font-mono text-[10px] tracking-wide uppercase",
        status === "connected" &&
          "border-emerald-500/40 bg-emerald-500/10 text-emerald-400",
        status === "connecting" &&
          "border-sky-500/40 bg-sky-500/10 text-sky-400",
        status === "error" &&
          "border-rose-500/40 bg-rose-500/10 text-rose-400",
        status === "disconnected" &&
          "border-zinc-500/40 bg-zinc-500/10 text-zinc-400"
      )}
    >
      {label}
    </Badge>
  );
}

export function CopyStatusPill({ status }: { status: CopyStatus }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "font-mono text-[10px] tracking-wide uppercase",
        status === "filled" &&
          "border-emerald-500/40 bg-emerald-500/10 text-emerald-400",
        status === "queued" &&
          "border-sky-500/40 bg-sky-500/10 text-sky-300",
        status === "skipped" &&
          "border-amber-500/40 bg-amber-500/10 text-amber-300",
        status === "error" &&
          "border-rose-500/40 bg-rose-500/10 text-rose-400"
      )}
    >
      {status}
    </Badge>
  );
}

export function SidePill({ side }: { side: Side }) {
  return (
    <span
      className={cn(
        "font-mono text-[11px] font-semibold tracking-wide uppercase",
        side === "buy" ? "text-emerald-400" : "text-rose-400"
      )}
    >
      {side}
    </span>
  );
}
