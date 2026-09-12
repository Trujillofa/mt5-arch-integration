"use client";

import { useEffect, useMemo, useState } from "react";
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
import { armedCopyBrokers, liveOrderArmed, needsSizeConfirm, sizeConfirmLines } from "@/lib/copy-fanout";
import { useDesk } from "@/lib/desk-context";
import {
  DEFAULT_DESK_LOTS,
  FIRM_BY_ID,
  defaultLotsForSymbolFirm,
  knownDefaultLotValues,
} from "@/lib/firms";
import { formatPrice } from "@/lib/format";
import {
  applyScalpStopsIfEmpty,
  suggestScalpStops,
  type ScalpStopSuggestion,
} from "@/lib/live-order/atr-stops";
import {
  LIMIT_OFFSET_POINTS,
  isPendingOrderType,
  isUs30Family,
  liveUs30SlError,
  openSlTpSideError,
  resolvePendingPrice,
} from "@/lib/live-order/guards";
import type { LiveOrderType } from "@/lib/live-order/types";
import { MASTER_SYMBOLS, quoteBySymbol, quoteContractSize } from "@/lib/quotes";
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
  const [bridgeAtr, setBridgeAtr] = useState<number | null>(null);
  const [atrSource, setAtrSource] = useState<"atr14" | "last_known" | "fallback80">("fallback80");

  const master = state.accounts.find((account) => account.id === state.masterId);
  const selected = state.accounts.find((account) => account.id === state.selectedAccountId);
  const ticketFirmId = selected?.firmId ?? master?.firmId ?? "ftmo";
  const ticketDefault = defaultLotsForSymbolFirm(ticketFirmId, symbol);
  const quote = quoteBySymbol(state.quotes, symbol);
  const enabledSlaves = state.copySettings.filter((row) => row.enabled).length;

  const us30 = isUs30Family(symbol);
  const liveArmed = liveOrderArmed(state);

  useEffect(() => {
    if (!us30) {
      setBridgeAtr(null);
      setAtrSource("fallback80");
      return;
    }
    const controller = new AbortController();
    void fetch(`/api/desk/scalp-stops?broker=${encodeURIComponent(ticketFirmId)}&symbol=${encodeURIComponent(symbol)}`, {
      signal: controller.signal,
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((body: { atr?: number | null; source?: "atr14" | "last_known" | "fallback80" } | null) => {
        if (!body) return;
        setBridgeAtr(body.atr != null && body.atr > 0 ? body.atr : null);
        setAtrSource(body.source ?? "fallback80");
      })
      .catch(() => {
        setBridgeAtr(null);
        setAtrSource("fallback80");
      });
    return () => controller.abort();
  }, [us30, symbol, ticketFirmId]);

  useEffect(() => {
    if (!isUs30Family(symbol)) {
      setSl("");
      setTp("");
    }
  }, [symbol]);

  useEffect(() => {
    if (!us30) return;
    if (!quote) return;
    const lotsN = Number(lots);
    const suggestion = suggestScalpStops({
      side: "buy",
      entry: quote.ask,
      atr: bridgeAtr,
      point: quote.pip,
      spreadPoints: Math.max(0, Math.round((quote.ask - quote.bid) / quote.pip)),
      lots: Number.isFinite(lotsN) && lotsN > 0 ? lotsN : undefined,
      contractSize: quoteContractSize(symbol),
    });
    if (!suggestion) return;
    setSl((prev) => (prev === "" ? String(suggestion.sl) : prev));
    setTp((prev) => (prev === "" ? String(suggestion.tp) : prev));
  }, [us30, symbol, quote?.ask, quote?.bid, quote?.pip, bridgeAtr]);

  useEffect(() => {
    setLots((prev) => {
      const n = Number(prev);
      if (prev.trim() === "" || !Number.isFinite(n)) return ticketDefault.toFixed(2);
      const known = knownDefaultLotValues();
      if (known.some((def) => Math.abs(n - def) < 1e-8)) return ticketDefault.toFixed(2);
      return prev;
    });
  }, [ticketFirmId, symbol, ticketDefault]);

  const hint = useMemo(() => {
    if (symbol === "NAS100") {
      return "NAS100 is unmapped on FundingPips — that child should skip.";
    }
    if (state.ftmoLiveMaster) {
      return `FTMO live master is armed. The button you press (market / limit / stop) is what 541163357 sends at the lots in this form (this symbol ${ticketDefault}; FN ×0.1, FundingPips ×0.2). ${enabledSlaves} slaves copy the same type.`;
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
        state.wsfLiveCopy ? `WSF ${defaultLotsForSymbolFirm("wsf", symbol)} ${symbol}` : null,
        state.fundednextLiveCopy ? `FN ${defaultLotsForSymbolFirm("fundednext", symbol)} ${symbol}` : null,
        state.alphacapitalLiveCopy ? `ACG ${defaultLotsForSymbolFirm("alphacapital", symbol)} ${symbol}` : null,
        state.fundingpipsLiveCopy ? `FundingPips ${defaultLotsForSymbolFirm("fundingpips", symbol)} ${symbol}` : null,
        state.neomaaLiveCopy ? `Neomaa ${defaultLotsForSymbolFirm("neomaa", symbol)} ${symbol}` : null,
        state.fortradersLiveCopy ? `Fortraders ${defaultLotsForSymbolFirm("fortraders", symbol)} ${symbol}` : null,
      ]
        .filter(Boolean)
        .join(" · ")}. ${enabledSlaves} slaves will attempt a fill.`;
    }
    return `${enabledSlaves} slaves will attempt a fill. Live OrderSend stays off until you arm a card.`;
  }, [symbol, lots, ticketDefault, enabledSlaves, state.wsfLiveCopy, state.ftmoLiveMaster, state.fundednextLiveCopy, state.alphacapitalLiveCopy, state.fundingpipsLiveCopy, state.neomaaLiveCopy, state.fortradersLiveCopy]);

  const lotsN = Number(lots);
  const scalpLots = Number.isFinite(lotsN) && lotsN > 0 ? lotsN : ticketDefault;
  const scalpBuy: ScalpStopSuggestion | null =
    us30 && quote
      ? suggestScalpStops({
          side: "buy",
          entry: quote.ask,
          atr: bridgeAtr,
          point: quote.pip,
          spreadPoints: Math.max(0, Math.round((quote.ask - quote.bid) / quote.pip)),
          lots: scalpLots,
          contractSize: quoteContractSize(symbol),
        })
      : null;
  const scalpSell: ScalpStopSuggestion | null =
    us30 && quote
      ? suggestScalpStops({
          side: "sell",
          entry: quote.bid,
          atr: bridgeAtr,
          point: quote.pip,
          spreadPoints: Math.max(0, Math.round((quote.ask - quote.bid) / quote.pip)),
          lots: scalpLots,
          contractSize: quoteContractSize(symbol),
        })
      : null;

  function submit(action: TicketAction) {
    setFormError(null);
    const parsedLots = lots.trim() === "" ? ticketDefault : Number(lots);
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
    let sendSl = parsedSl;
    let sendTp = parsedTp;
    if (us30 && scalpBuy && scalpSell) {
      const filled = applyScalpStopsIfEmpty({
        side,
        entry: sendPrice ?? (side === "buy" ? quote?.ask ?? 0 : quote?.bid ?? 0),
        sl: parsedSl,
        tp: parsedTp,
        buySuggestion: scalpBuy,
        sellSuggestion: scalpSell,
      });
      sendSl = filled.sl;
      sendTp = filled.tp;
    }
    const slMissing = liveUs30SlError(symbol, sendSl, liveArmed);
    if (slMissing) {
      setFormError(slMissing);
      return;
    }
    const ref =
      sendPrice ??
      (quote ? (side === "buy" ? quote.ask : quote.bid) : null);
    const sideErr = openSlTpSideError(
      side === "sell" ? "SELL" : "BUY",
      sendSl,
      sendTp,
      ref,
      orderType
    );
    if (sideErr) {
      setFormError(sideErr.reason);
      return;
    }
    const input: MasterTradeInput = {
      symbol,
      side,
      lots: parsedLots,
      sl: sendSl,
      tp: sendTp,
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
          Limit and stop are extra. This symbol defaults to {ticketDefault} lots
          (FX/US30 4 · gold 0.40 · BTC 0.04; FN ×0.1, FundingPips ×0.2).
          Empty pending price uses a {LIMIT_OFFSET_POINTS}-point offset from bid/ask.
          {state.ftmoLiveMaster ? " Live FTMO master on " : " Paper book on "}
          <span className="text-foreground">
            {master ? FIRM_BY_ID[master.firmId].name : "—"}
          </span>
          , then fan out through the copy engine.
          {state.wsfLiveCopy ? ` WSF slave is live ${defaultLotsForSymbolFirm("wsf", symbol)} lots.` : ""}
          {state.fundednextLiveCopy ? ` FundedNext slave is live ${defaultLotsForSymbolFirm("fundednext", symbol)} lots.` : ""}
          {state.alphacapitalLiveCopy ? ` Alpha Capital slave is live ${defaultLotsForSymbolFirm("alphacapital", symbol)} lots.` : ""}
          {state.fundingpipsLiveCopy ? ` FundingPips slave is live ${defaultLotsForSymbolFirm("fundingpips", symbol)} lots.` : ""}
          {state.neomaaLiveCopy ? ` Neomaa slave is live ${defaultLotsForSymbolFirm("neomaa", symbol)} lots.` : ""}
          {state.fortradersLiveCopy ? ` Fortraders slave is live ${defaultLotsForSymbolFirm("fortraders", symbol)} lots.` : ""}
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

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Field
            id="lots"
            label="Lots"
            value={lots}
            onChange={setLots}
            placeholder={ticketDefault.toFixed(2)}
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
            label={us30 && liveArmed ? "SL (req.)" : us30 ? "SL" : "SL (opt.)"}
            value={sl}
            onChange={setSl}
            placeholder={scalpBuy ? String(scalpBuy.sl) : "—"}
          />
          <Field
            id="tp"
            label={us30 ? "TP" : "TP (opt.)"}
            value={tp}
            onChange={setTp}
            placeholder={scalpBuy ? String(scalpBuy.tp) : "—"}
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
        {us30 && scalpBuy && scalpSell ? (
          <p className="text-xs leading-relaxed text-muted-foreground">
            ATR 1.0 / 1.5 ({atrSource === "atr14" ? "bridge M5 ATR14" : atrSource === "last_known" ? "last known ATR" : "fallback 80 pt"}
            ). Not 1% of index price. Buy {scalpBuy.preview}. Sell {scalpSell.preview}.
            {liveArmed ? " Live US30 send requires SL." : ""}
          </p>
        ) : null}

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
              className="min-h-11 bg-emerald-500 text-zinc-950 hover:bg-emerald-400 sm:min-h-8"
              onClick={() => submit("buy")}
            >
              Buy
            </Button>
            <Button
              type="button"
              disabled={busy}
              className="min-h-11 bg-rose-500 text-zinc-50 hover:bg-rose-400 sm:min-h-8"
              onClick={() => submit("sell")}
            >
              Sell
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              className="min-h-11 sm:min-h-8"
              onClick={() => submit("buy_limit")}
            >
              Buy limit
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              className="min-h-11 sm:min-h-8"
              onClick={() => submit("sell_limit")}
            >
              Sell limit
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              className="min-h-11 sm:min-h-8"
              onClick={() => submit("buy_stop")}
            >
              Buy stop
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              className="min-h-11 sm:min-h-8"
              onClick={() => submit("sell_stop")}
            >
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
            Ticket is not 0.01. Each armed book will send the computed lot
            below (ticket × firm scale). 0.01 prove stays 0.01.
          </DialogDescription>
        </DialogHeader>
        <ul className="space-y-1 font-mono text-sm">
          {lines.length === 0 ? (
            <li>Paper only · {lots.toFixed(2)}</li>
          ) : (
            lines.map((row) => (
              <li key={row.id}>
                {row.name}: {row.lots.toFixed(2)}
                {row.roundedUp ? " · rounded up to broker min 0.01" : ""}
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
