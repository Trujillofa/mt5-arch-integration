"use client";

import { useState } from "react";
import { SidePill } from "@/components/desk/status-pills";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { isBrokerLeftover } from "@/lib/copy-engine";
import { useDesk } from "@/lib/desk-context";
import { FIRM_BY_ID } from "@/lib/firms";
import { pendingKind } from "@/lib/live-order/guards";
import { formatLots, formatMoney, formatPnl, formatPrice } from "@/lib/format";
import type { Position } from "@/lib/types";
import { cn } from "@/lib/utils";

function levelText(value: number | null | undefined): string {
  if (value == null || value <= 0) return "";
  return String(value);
}

function parseLevel(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return 0;
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || parsed < 0) return null;
  return parsed;
}

export function PositionsPanel() {
  const { state, flatten, busy, actionError, modifyPosition } = useDesk();

  if (state.positions.length === 0) {
    return (
      <div className="px-4 py-10 text-center">
        <p className="text-sm font-medium">No open positions or working limits</p>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          Desk fills, working limits, and live PositionsTotal (including broker
          leftovers) land here. Flatten stays desk-only unless you close a leftover
          row yourself.
        </p>
      </div>
    );
  }

  return (
    <div>
      {actionError ? (
        <p className="border-b border-rose-500/30 bg-rose-500/10 px-4 py-2 text-xs text-rose-300">
          {actionError}
        </p>
      ) : null}
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Account</TableHead>
          <TableHead>Symbol</TableHead>
          <TableHead>Side</TableHead>
          <TableHead className="text-right">Lots</TableHead>
          <TableHead className="text-right">Entry</TableHead>
          <TableHead className="text-right">SL</TableHead>
          <TableHead className="text-right">TP</TableHead>
          <TableHead className="text-right">uPnL</TableHead>
          <TableHead />
        </TableRow>
      </TableHeader>
      <TableBody>
        {state.positions.map((position) => {
          const account = state.accounts.find(
            (row) => row.id === position.accountId
          );
          const firm = account ? FIRM_BY_ID[account.firmId].name : "—";
          return (
            <PositionRow
              key={`${position.id}-${position.sl}-${position.tp}-${isBrokerLeftover(position) ? "L" : "D"}`}
              position={position}
              firm={firm}
              login={account?.login ?? position.accountId}
              firmId={account?.firmId}
              busy={busy}
              onFlatten={() => flatten(position.id)}
              onModify={(sl, tp) => modifyPosition(position.id, sl, tp)}
            />
          );
        })}
      </TableBody>
    </Table>
    </div>
  );
}

function PositionRow({
  position,
  firm,
  login,
  firmId,
  busy,
  onFlatten,
  onModify,
}: {
  position: Position;
  firm: string;
  login: string;
  firmId?: string;
  busy: boolean;
  onFlatten: () => void;
  onModify: (sl: number | null, tp: number | null) => void;
}) {
  const leftover = isBrokerLeftover(position);
  const [slDraft, setSlDraft] = useState(levelText(position.sl));
  const [tpDraft, setTpDraft] = useState(levelText(position.tp));
  const [confirmOpen, setConfirmOpen] = useState(false);
  const alpha = firmId === "alphacapital";
  const canModify = !position.livePending && !alpha;
  const slParsed = parseLevel(slDraft);
  const tpParsed = parseLevel(tpDraft);
  const levelsOk = slParsed != null && tpParsed != null;

  return (
    <TableRow>
      <TableCell>
        <div className="leading-tight">
          <p className="text-sm">{firm}</p>
          <p className="font-mono text-[11px] text-muted-foreground">
            {login}
            {position.liveOrder ? ` · #${position.liveOrder}` : ""}
          </p>
        </div>
      </TableCell>
      <TableCell className="font-mono text-xs">
        {position.symbol}
        {leftover ? (
          <span className="ml-2 rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-medium tracking-wide text-amber-200 uppercase">
            leftover
          </span>
        ) : (
          <span className="ml-2 rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-medium tracking-wide text-emerald-200 uppercase">
            desk
          </span>
        )}
        {position.livePending ? (
          <span className="ml-2 rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-medium tracking-wide text-amber-200 uppercase">
            {pendingKind(position.orderType) ?? "pending"}
          </span>
        ) : null}
      </TableCell>
      <TableCell>
        <SidePill side={position.side} />
      </TableCell>
      <TableCell className="text-right font-mono text-xs tabular-nums">
        {formatLots(position.lots)}
      </TableCell>
      <TableCell className="text-right font-mono text-xs tabular-nums">
        {formatPrice(position.symbol, position.entry)}
      </TableCell>
      <TableCell className="min-w-[7rem]">
        {position.livePending ? (
          <span className="block text-right font-mono text-xs tabular-nums">
            {position.sl && position.sl > 0 ? formatPrice(position.symbol, position.sl) : "—"}
          </span>
        ) : (
          <Input
            inputMode="decimal"
            aria-label={`Stop loss for ${position.symbol} ticket ${position.liveOrder ?? ""}`}
            className="min-h-11 h-11 text-right font-mono text-xs tabular-nums"
            value={slDraft}
            disabled={busy || alpha}
            placeholder={position.sl && position.sl > 0 ? formatPrice(position.symbol, position.sl) : "none"}
            onChange={(event) => setSlDraft(event.target.value)}
          />
        )}
      </TableCell>
      <TableCell className="min-w-[7rem]">
        {position.livePending ? (
          <span className="block text-right font-mono text-xs tabular-nums">
            {position.tp && position.tp > 0 ? formatPrice(position.symbol, position.tp) : "—"}
          </span>
        ) : (
          <Input
            inputMode="decimal"
            aria-label={`Take profit for ${position.symbol} ticket ${position.liveOrder ?? ""}`}
            className="min-h-11 h-11 text-right font-mono text-xs tabular-nums"
            value={tpDraft}
            disabled={busy || alpha}
            placeholder={position.tp && position.tp > 0 ? formatPrice(position.symbol, position.tp) : "none"}
            onChange={(event) => setTpDraft(event.target.value)}
          />
        )}
      </TableCell>
      <TableCell
        className={cn(
          "text-right font-mono text-xs tabular-nums",
          position.pnl > 0 && "text-emerald-400",
          position.pnl < 0 && "text-rose-400"
        )}
      >
        {formatPnl(position.pnl)}
      </TableCell>
      <TableCell className="text-right">
        <div className="flex flex-col items-end gap-1.5">
          {canModify ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={busy || !levelsOk}
              className="min-h-11 h-11 px-3"
              onClick={() => setConfirmOpen(true)}
            >
              Set SL/TP
            </Button>
          ) : alpha ? (
            <span className="text-[10px] text-muted-foreground">Alpha read-only</span>
          ) : null}
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy}
            className="min-h-11 h-11 px-3"
            onClick={() => onFlatten()}
          >
            {position.livePending ? "Cancel pending" : position.liveBroker ? "Close live" : "Close"}
          </Button>
        </div>
        <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Confirm SL/TP</DialogTitle>
              <DialogDescription>
                {leftover
                  ? "This is a broker leftover. Modify applies only to this ticket — flatten will not mass-close it."
                  : "Sends TRADE_ACTION_SLTP on this book only. Tickets differ across slaves — no fan-out."}
              </DialogDescription>
            </DialogHeader>
            <p className="font-mono text-sm">
              {firm} {position.symbol} {position.side.toUpperCase()} {formatLots(position.lots)}
              {position.liveOrder ? ` · ticket ${position.liveOrder}` : ""}
            </p>
            <p className="text-sm">
              SL {slParsed === 0 ? "clear" : slParsed} → was{" "}
              {position.sl && position.sl > 0 ? position.sl : "none"}
              <br />
              TP {tpParsed === 0 ? "clear" : tpParsed} → was{" "}
              {position.tp && position.tp > 0 ? position.tp : "none"}
            </p>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                className="min-h-11 h-11"
                onClick={() => setConfirmOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                className="min-h-11 h-11"
                disabled={!levelsOk || busy}
                onClick={() => {
                  if (slParsed == null || tpParsed == null) return;
                  onModify(slParsed, tpParsed);
                  setConfirmOpen(false);
                }}
              >
                Send SL/TP
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </TableCell>
    </TableRow>
  );
}

export function ExposurePanel() {
  const { state } = useDesk();

  const bySymbol = new Map<
    string,
    { buy: number; sell: number; accounts: number }
  >();
  for (const position of state.positions) {
    const row = bySymbol.get(position.symbol) ?? {
      buy: 0,
      sell: 0,
      accounts: 0,
    };
    row.accounts += 1;
    if (position.side === "buy") row.buy += position.lots;
    else row.sell += position.lots;
    bySymbol.set(position.symbol, row);
  }

  const byAccount = state.accounts.map((account) => {
    const positions = state.positions.filter(
      (position) => position.accountId === account.id
    );
    const net = positions.reduce(
      (sum, position) =>
        sum + (position.side === "buy" ? position.lots : -position.lots),
      0
    );
    const pnl = positions.reduce((sum, position) => sum + position.pnl, 0);
    return { account, net, pnl, count: positions.length };
  });

  if (state.positions.length === 0) {
    return (
      <div className="px-4 py-10 text-center">
        <p className="text-sm font-medium">No exposure</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Net lots by symbol and account appear after the first copied fill.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-6 p-4 md:grid-cols-2">
      <div>
        <p className="mb-2 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
          By symbol
        </p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Symbol</TableHead>
              <TableHead className="text-right">Buy</TableHead>
              <TableHead className="text-right">Sell</TableHead>
              <TableHead className="text-right">Net</TableHead>
              <TableHead className="text-right">Books</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {[...bySymbol.entries()].map(([symbol, row]) => (
              <TableRow key={symbol}>
                <TableCell className="font-mono text-xs">{symbol}</TableCell>
                <TableCell className="text-right font-mono text-xs text-emerald-400">
                  {row.buy.toFixed(2)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs text-rose-400">
                  {row.sell.toFixed(2)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs tabular-nums">
                  {(row.buy - row.sell).toFixed(2)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {row.accounts}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div>
        <p className="mb-2 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
          By account
        </p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Firm</TableHead>
              <TableHead className="text-right">Net lots</TableHead>
              <TableHead className="text-right">Float</TableHead>
              <TableHead className="text-right">Equity</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {byAccount.map(({ account, net, pnl }) => (
              <TableRow key={account.id}>
                <TableCell>{FIRM_BY_ID[account.firmId].name}</TableCell>
                <TableCell className="text-right font-mono text-xs tabular-nums">
                  {net.toFixed(2)}
                </TableCell>
                <TableCell
                  className={cn(
                    "text-right font-mono text-xs tabular-nums",
                    pnl > 0 && "text-emerald-400",
                    pnl < 0 && "text-rose-400"
                  )}
                >
                  {formatPnl(pnl)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs tabular-nums">
                  {formatMoney(account.equity)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
