"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useDesk } from "@/lib/desk-context";
import { FIRM_BY_ID } from "@/lib/firms";
import { formatPrice } from "@/lib/format";
import { MASTER_SYMBOLS, quoteBySymbol } from "@/lib/quotes";
import type { Side } from "@/lib/types";

export function TradeTicket() {
  const { state, busy, placeTrade } = useDesk();
  const [symbol, setSymbol] = useState<string>("EURUSD");
  const [side, setSide] = useState<Side>("buy");
  const [lots, setLots] = useState("1.00");
  const [sl, setSl] = useState("");
  const [tp, setTp] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const master = state.accounts.find((account) => account.id === state.masterId);
  const quote = quoteBySymbol(state.quotes, symbol);
  const enabledSlaves = state.copySettings.filter((row) => row.enabled).length;

  const hint = useMemo(() => {
    if (symbol === "NAS100") {
      return "NAS100 is unmapped on FundingPips — that child should skip.";
    }
    if (Number(lots) >= 2) {
      return "2.00 lots × FundingPips 0.8 exceeds its 1.00 max lot — expect a skip.";
    }
    return `Fortraders is copy-off. ${enabledSlaves} slaves will attempt a fill.`;
  }, [symbol, lots, enabledSlaves]);

  function submit() {
    setFormError(null);
    const parsedLots = Number(lots);
    if (!Number.isFinite(parsedLots) || parsedLots < 0.01) {
      setFormError("Lots must be at least 0.01.");
      return;
    }
    if (!master) {
      setFormError("Select a master account first.");
      return;
    }
    if (master.status !== "connected") {
      setFormError("Master is disconnected. Connect it from the account panel.");
      return;
    }
    const parsedSl = sl.trim() === "" ? null : Number(sl);
    const parsedTp = tp.trim() === "" ? null : Number(tp);
    if (parsedSl !== null && !Number.isFinite(parsedSl)) {
      setFormError("Stop loss must be a number.");
      return;
    }
    if (parsedTp !== null && !Number.isFinite(parsedTp)) {
      setFormError("Take profit must be a number.");
      return;
    }
    const error = placeTrade({
      symbol,
      side,
      lots: parsedLots,
      sl: parsedSl,
      tp: parsedTp,
    });
    if (error) {
      setFormError(error);
      toast.error(error);
      return;
    }
    toast.success(`${side.toUpperCase()} ${parsedLots.toFixed(2)} ${symbol} on master`);
  }

  return (
    <Card size="sm" className="h-full">
      <CardHeader className="border-b">
        <CardTitle>Place master trade</CardTitle>
        <p className="text-xs text-muted-foreground">
          Paper fill on{" "}
          <span className="text-foreground">
            {master ? FIRM_BY_ID[master.firmId].name : "—"}
          </span>
          , then fan out through the copy engine. This button never live-OrderSends.
          WSF live scratch is a separate control on the WSF card.
        </p>
      </CardHeader>
      <CardContent className="space-y-4 pt-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="symbol">Symbol</Label>
            <Select value={symbol} onValueChange={(value) => setSymbol(String(value))}>
              <SelectTrigger id="symbol" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MASTER_SYMBOLS.map((item) => (
                  <SelectItem key={item} value={item}>
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Side</Label>
            <div className="grid grid-cols-2 gap-1.5">
              <Button
                type="button"
                variant={side === "buy" ? "default" : "outline"}
                className={
                  side === "buy"
                    ? "bg-emerald-500 text-zinc-950 hover:bg-emerald-400"
                    : undefined
                }
                onClick={() => setSide("buy")}
              >
                Buy
              </Button>
              <Button
                type="button"
                variant={side === "sell" ? "default" : "outline"}
                className={
                  side === "sell"
                    ? "bg-rose-500 text-zinc-50 hover:bg-rose-400"
                    : undefined
                }
                onClick={() => setSide("sell")}
              >
                Sell
              </Button>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <Field
            id="lots"
            label="Lots"
            value={lots}
            onChange={setLots}
            placeholder="1.00"
          />
          <Field
            id="sl"
            label="SL (opt.)"
            value={sl}
            onChange={setSl}
            placeholder="—"
          />
          <Field
            id="tp"
            label="TP (opt.)"
            value={tp}
            onChange={setTp}
            placeholder="—"
          />
        </div>

        <div className="flex items-center justify-between rounded-lg bg-muted/50 px-3 py-2 font-mono text-xs">
          <span className="text-muted-foreground">Paper {symbol}</span>
          <span className="tabular-nums">
            {quote
              ? `${formatPrice(symbol, quote.bid)} / ${formatPrice(symbol, quote.ask)}`
              : "no quote"}
          </span>
        </div>

        {formError ? (
          <p className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
            {formError}
          </p>
        ) : null}

        <Button
          type="button"
          className="w-full"
          disabled={busy}
          onClick={submit}
        >
          {busy ? "Copying…" : `Send ${side} to ${enabledSlaves} slaves`}
        </Button>
        <p className="text-xs leading-relaxed text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}

function Field({
  id,
  label,
  value,
  onChange,
  placeholder,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        inputMode="decimal"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className="font-mono"
      />
    </div>
  );
}
