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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { armedCopyBrokers, needsSizeConfirm, sizeConfirmLines } from "@/lib/copy-fanout";
import { useDesk } from "@/lib/desk-context";
import { DEFAULT_DESK_LOTS, FIRM_BY_ID, defaultLotsForFirm } from "@/lib/firms";
import { formatPrice } from "@/lib/format";
import {
  LIMIT_OFFSET_POINTS,
  isPendingOrderType,
  resolvePendingPrice,
} from "@/lib/live-order/guards";
import type { LiveOrderType } from "@/lib/live-order/types";
import { MASTER_SYMBOLS, quoteBySymbol } from "@/lib/quotes";
import type { MasterTradeInput, Side } from "@/lib/types";

type TicketAction = "buy" | "sell" | "buy_limit" | "sell_limit" | "buy_stop" | "sell_stop";

function actionToOrder(action: TicketAction): { side: Side; orderType: LiveOrderType } {
  if (action === "buy") return { side: "buy", orderType: "market" };
  if (action === "sell") return { side: "sell", orderType: "market" };
  if (action === "buy_limit") return { side: "buy", orderType: "buy_limit" };
  if (action === "sell_limit") return { side: "sell", orderType: "sell_limit" };
  if (action === "buy_stop") return { side: "buy", orderType: "buy_stop" };
  return { side: "sell", orderType: "sell_stop" };
}

export function TradeTicket() {
  const { state, busy, placeTrade } = useDesk();
  const [symbol, setSymbol] = useState<string>("EURUSD");
  const [lots, setLots] = useState(DEFAULT_DESK_LOTS.toFixed(2));
  const [price, setPrice] = useState("");
  const [sl, setSl] = useState("");
  const [tp, setTp] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [pendingInput, setPendingInput] = useState<MasterTradeInput | null>(null);

  const master = state.accounts.find((account) => account.id === state.masterId);
  const quote = quoteBySymbol(state.quotes, symbol);
  const enabledSlaves = state.copySettings.filter((row) => row.enabled).length;

  const hint = useMemo(() => {
    if (symbol === "NAS100") {
      return "NAS100 is unmapped on FundingPips — that child should skip.";
    }
    if (Number(lots) >= 2) {
      return `2.00 lots × FundingPips ${defaultLotsForFirm("fundingpips")} may exceed a stale 1.00 max lot — bump max lot.`;
    }
    if (state.ftmoLiveMaster) {
      return `FTMO live master is armed. The button you press (market / limit / stop) is what 541163357 sends at the lots in this form (default ${DEFAULT_DESK_LOTS}). ${enabledSlaves} slaves copy the same type.`;
    }
    if (
      state.wsfLiveCopy ||
      state.fundednextLiveCopy ||
      state.alphacapitalLiveCopy ||
      state.fundingpipsLiveCopy ||
      state.neomaaLiveCopy ||
      state.fortradersLiveCopy
    ) {
      return `Live copy armed (same type as the ticket): ${[
        state.wsfLiveCopy ? `WSF ${defaultLotsForFirm("wsf")} EURUSDc` : null,
        state.fundednextLiveCopy ? `FN ${defaultLotsForFirm("fundednext")} EURUSD` : null,
        state.alphacapitalLiveCopy ? `ACG ${defaultLotsForFirm("alphacapital")} EURUSD` : null,
        state.fundingpipsLiveCopy ? `FundingPips ${defaultLotsForFirm("fundingpips")} EURUSD` : null,
        state.neomaaLiveCopy ? `Neomaa ${defaultLotsForFirm("neomaa")} EURUSD` : null,
        state.fortradersLiveCopy ? `Fortraders ${defaultLotsForFirm("fortraders")} EURUSD` : null,
      ]
        .filter(Boolean)
        .join(" · ")}. ${enabledSlaves} slaves will attempt a fill.`;
    }
    return `${enabledSlaves} slaves will attempt a fill. Live OrderSend stays off until you arm a card.`;
  }, [symbol, lots, enabledSlaves, state.wsfLiveCopy, state.ftmoLiveMaster, state.fundednextLiveCopy, state.alphacapitalLiveCopy, state.fundingpipsLiveCopy, state.neomaaLiveCopy, state.fortradersLiveCopy]);

  function submit(action: TicketAction) {
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
    const parsedPrice = price.trim() === "" ? null : Number(price);
    if (parsedSl !== null && !Number.isFinite(parsedSl)) {
      setFormError("Stop loss must be a number.");
      return;
    }
    if (parsedTp !== null && !Number.isFinite(parsedTp)) {
      setFormError("Take profit must be a number.");
      return;
    }
    if (parsedPrice !== null && (!Number.isFinite(parsedPrice) || parsedPrice <= 0)) {
      setFormError("Pending price must be greater than 0.");
      return;
    }
    const { side, orderType } = actionToOrder(action);
    let sendPrice = parsedPrice;
    if (isPendingOrderType(orderType) && sendPrice == null && quote) {
      const resolved = resolvePendingPrice({
        orderType,
        explicitPrice: null,
        bid: quote.bid,
        ask: quote.ask,
        point: quote.pip / 10,
      });
      if (resolved.ok) sendPrice = resolved.price;
    }
    if (isPendingOrderType(orderType) && (sendPrice == null || sendPrice <= 0)) {
      setFormError("Pending limit/stop needs a price or a paper quote for the 50-point offset.");
      return;
    }
    const input: MasterTradeInput = {
      symbol,
      side,
      lots: parsedLots,
      sl: parsedSl,
      tp: parsedTp,
      price: isPendingOrderType(orderType) ? sendPrice : null,
      orderType,
    };
    if (needsSizeConfirm(parsedLots)) {
      setPendingInput(input);
      return;
    }
    sendTrade(input);
  }

  function sendTrade(input: MasterTradeInput) {
    const error = placeTrade(input);
    if (error) {
      setFormError(error);
      toast.error(error);
      return;
    }
    const label =
      (input.orderType ?? "market") === "market"
        ? input.side.toUpperCase()
        : (input.orderType ?? "limit").replace("_", " ").toUpperCase();
    toast.success(`${label} ${input.lots.toFixed(2)} ${input.symbol}`);
  }

  return (
    <Card size="sm" className="h-full">
      <CardHeader className="border-b">
        <CardTitle>Place master trade</CardTitle>
        <p className="text-xs text-muted-foreground">
          Market <span className="font-medium text-foreground">Buy / Sell</span> stay available.
          Limit and stop are extra. Default lots {DEFAULT_DESK_LOTS} (FN{" "}
          {defaultLotsForFirm("fundednext")}, FundingPips {defaultLotsForFirm("fundingpips")}).
          Empty pending price uses a {LIMIT_OFFSET_POINTS}-point offset from bid/ask.
          {state.ftmoLiveMaster ? " Live FTMO master on " : " Paper book on "}
          <span className="text-foreground">
            {master ? FIRM_BY_ID[master.firmId].name : "—"}
          </span>
          , then fan out through the copy engine.
          {state.wsfLiveCopy ? ` WSF slave is live ${defaultLotsForFirm("wsf")} lots.` : ""}
          {state.fundednextLiveCopy ? ` FundedNext slave is live ${defaultLotsForFirm("fundednext")} lots.` : ""}
          {state.alphacapitalLiveCopy ? ` Alpha Capital slave is live ${defaultLotsForFirm("alphacapital")} lots.` : ""}
          {state.fundingpipsLiveCopy ? ` FundingPips slave is live ${defaultLotsForFirm("fundingpips")} lots.` : ""}
          {state.neomaaLiveCopy ? ` Neomaa slave is live ${defaultLotsForFirm("neomaa")} lots.` : ""}
          {state.fortradersLiveCopy ? ` Fortraders slave is live ${defaultLotsForFirm("fortraders")} lots.` : ""}
          {!state.wsfLiveCopy &&
          !state.fundednextLiveCopy &&
          !state.alphacapitalLiveCopy &&
          !state.fundingpipsLiveCopy &&
          !state.neomaaLiveCopy &&
          !state.fortradersLiveCopy &&
          !state.ftmoLiveMaster
            ? " Live OrderSend stays off until you arm a card."
            : ""}
        </p>
      </CardHeader>
      <CardContent className="space-y-4 pt-4">
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

        <div className="grid grid-cols-4 gap-3">
          <Field
            id="lots"
            label="Lots"
            value={lots}
            onChange={setLots}
            placeholder={DEFAULT_DESK_LOTS.toFixed(2)}
          />
          <Field
            id="pending-price"
            label="Pending price"
            value={price}
            onChange={setPrice}
            placeholder={quote ? formatPrice(symbol, quote.bid) : "offset"}
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

        <div className="space-y-1.5">
          <Label>Send</Label>
          <div className="grid grid-cols-2 gap-1.5">
            <Button
              type="button"
              disabled={busy}
              className="bg-emerald-500 text-zinc-950 hover:bg-emerald-400"
              onClick={() => submit("buy")}
            >
              Buy
            </Button>
            <Button
              type="button"
              disabled={busy}
              className="bg-rose-500 text-zinc-50 hover:bg-rose-400"
              onClick={() => submit("sell")}
            >
              Sell
            </Button>
            <Button type="button" variant="outline" disabled={busy} onClick={() => submit("buy_limit")}>
              Buy limit
            </Button>
            <Button type="button" variant="outline" disabled={busy} onClick={() => submit("sell_limit")}>
              Sell limit
            </Button>
            <Button type="button" variant="outline" disabled={busy} onClick={() => submit("buy_stop")}>
              Buy stop
            </Button>
            <Button type="button" variant="outline" disabled={busy} onClick={() => submit("sell_stop")}>
              Sell stop
            </Button>
          </div>
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">{hint}</p>
      </CardContent>
      <SizeConfirmDialog
        open={pendingInput != null}
        lots={pendingInput?.lots ?? 0}
        includeMaster={state.ftmoLiveMaster}
        armed={armedCopyBrokers(state)}
        onCancel={() => setPendingInput(null)}
        onConfirm={() => {
          if (!pendingInput) return;
          const input = pendingInput;
          setPendingInput(null);
          sendTrade(input);
        }}
      />
    </Card>
  );
}

function SizeConfirmDialog({
  open,
  lots,
  includeMaster,
  armed,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  lots: number;
  includeMaster: boolean;
  armed: ReturnType<typeof armedCopyBrokers>;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const lines = sizeConfirmLines(lots, armed, includeMaster);
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirm size {lots.toFixed(2)}</DialogTitle>
          <DialogDescription>
            Ticket is not 0.01. Each armed book will send the lot below — not a
            silent 1.4.
          </DialogDescription>
        </DialogHeader>
        <ul className="space-y-1 font-mono text-sm">
          {lines.length === 0 ? (
            <li>Paper only · {lots.toFixed(2)}</li>
          ) : (
            lines.map((row) => (
              <li key={row.id}>
                {row.name}: {row.lots.toFixed(2)}
              </li>
            ))
          )}
        </ul>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" onClick={onConfirm}>
            Send{" "}
            {lines.length
              ? lines.map((row) => `${row.lots.toFixed(2)}`).join(" · ")
              : lots.toFixed(2)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
