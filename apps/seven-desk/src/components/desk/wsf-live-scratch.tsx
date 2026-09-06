"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { LIVE_ORDER_CLIENT_BUDGET_MS } from "@/lib/live-order/guards";
import type { WsfLiveOrderResult } from "@/lib/wsf/types";

const CONFIRM = "WSF-149736";

export function WsfLiveScratch() {
  const [liveMode, setLiveMode] = useState(false);
  const [ack, setAck] = useState(false);
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<WsfLiveOrderResult | null>(null);

  const armed = liveMode && ack && confirm === CONFIRM;
  const hint = useMemo(() => {
    if (!liveMode) return "Live mode is off. Paper copy is unchanged.";
    if (!ack) return "Tick the acknowledgement. This is a real WSF order.";
    if (confirm !== CONFIRM) return `Type ${CONFIRM} exactly.`;
    return "Armed. One min-lot EURUSDc BUY, then close.";
  }, [liveMode, ack, confirm]);

  async function send() {
    if (!armed || busy) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/wsf/order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        signal: AbortSignal.timeout(LIVE_ORDER_CLIENT_BUDGET_MS),
        body: JSON.stringify({
          live: true,
          confirm: CONFIRM,
          action: "scratch",
          symbol: "EURUSDc",
          side: "buy",
          volume_min: true,
        }),
      });
      const next = (await response.json()) as WsfLiveOrderResult;
      setResult(next);
      if (!response.ok || !next.ok) {
        const message = next.reason || `Live order failed (${response.status})`;
        setError(message);
        toast.error(message);
        return;
      }
      toast.success(
        `WSF ${next.login} ${next.side} ${next.volume} ${next.symbol} ticket ${next.order ?? "—"}`
      );
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Live order failed.";
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-3 rounded-lg border border-rose-500/30 bg-rose-500/5 p-3">
      <div>
        <p className="text-[11px] font-medium tracking-wide text-rose-200 uppercase">
          WSF live scratch
        </p>
        <p className="text-xs text-muted-foreground">
          Separate from paper copy. WSF login 149736 / WSFmarkets-Server only.
          Min lot, open then close. Does not use Vantage, FP, or official MCP.
        </p>
      </div>

      <div className="flex items-center justify-between gap-3">
        <Label htmlFor="wsf-live-mode" className="text-xs">
          Enable live WSF send
        </Label>
        <Switch
          id="wsf-live-mode"
          checked={liveMode}
          onCheckedChange={(value) => {
            setLiveMode(Boolean(value));
            if (!value) {
              setAck(false);
              setConfirm("");
            }
          }}
        />
      </div>

      {liveMode ? (
        <div className="space-y-3">
          <label className="flex items-start gap-2 text-xs text-rose-100/90">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={ack}
              onChange={(event) => setAck(event.target.checked)}
            />
            <span>
              I am sending a live min-lot order on WSF account 149736, not paper.
            </span>
          </label>
          <div className="space-y-1.5">
            <Label htmlFor="wsf-live-confirm">Confirm token</Label>
            <Input
              id="wsf-live-confirm"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              placeholder={CONFIRM}
              autoComplete="off"
              spellCheck={false}
              className="font-mono"
            />
          </div>
          <Button
            type="button"
            variant="destructive"
            className="w-full"
            disabled={!armed || busy}
            onClick={() => void send()}
          >
            {busy ? "Sending live scratch…" : "Live scratch WSF 149736 (min lot, open then close)"}
          </Button>
        </div>
      ) : null}

      <p className="text-xs text-muted-foreground">{hint}</p>

      {error ? (
        <p className="rounded-md border border-rose-500/30 bg-rose-500/10 px-2 py-1.5 text-xs text-rose-200">
          {error}
        </p>
      ) : null}

      {result ? <ResultView result={result} /> : null}
    </section>
  );
}

function ResultView({ result }: { result: WsfLiveOrderResult }) {
  return (
    <div className="space-y-1 rounded-md bg-background/40 px-2 py-1.5 font-mono text-[11px] text-muted-foreground">
      <p className={result.ok ? "text-emerald-200" : "text-rose-200"}>
        {result.ok ? "filled" : "failed"} · {result.stage} · login {result.login ?? "—"} @{" "}
        {result.server ?? "—"}
      </p>
      <p>
        {result.side ?? "—"} {result.volume ?? "—"} {result.symbol ?? "—"} · order{" "}
        {result.order ?? "—"} · pos {result.position ?? "—"}
      </p>
      <p>
        open {result.openPrice ?? "—"} → close {result.closePrice ?? "—"} · hold{" "}
        {result.holdMs ?? "—"}ms · pnl {result.profit ?? "—"} · bal {result.balanceAfter ?? "—"}
      </p>
      <p>
        deals {result.dealOpen ?? "—"} / {result.dealClose ?? "—"} · {result.reason}
      </p>
    </div>
  );
}
