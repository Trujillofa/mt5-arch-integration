"use client";

import { SidePill } from "@/components/desk/status-pills";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDesk } from "@/lib/desk-context";
import { FIRM_BY_ID } from "@/lib/firms";
import { formatLots, formatMoney, formatPnl, formatPrice } from "@/lib/format";
import { cn } from "@/lib/utils";

export function PositionsPanel() {
  const { state, flatten } = useDesk();

  if (state.positions.length === 0) {
    return (
      <div className="px-4 py-10 text-center">
        <p className="text-sm font-medium">No open positions</p>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          Copied fills land here. Equity on each account card tracks floating
          P&amp;L from the paper book.
        </p>
      </div>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Account</TableHead>
          <TableHead>Symbol</TableHead>
          <TableHead>Side</TableHead>
          <TableHead className="text-right">Lots</TableHead>
          <TableHead className="text-right">Entry</TableHead>
          <TableHead className="text-right">Mark</TableHead>
          <TableHead className="text-right">P&amp;L</TableHead>
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
            <TableRow key={position.id}>
              <TableCell>
                <div className="leading-tight">
                  <p className="text-sm">{firm}</p>
                  <p className="font-mono text-[11px] text-muted-foreground">
                    {account?.login ?? position.accountId}
                  </p>
                </div>
              </TableCell>
              <TableCell className="font-mono text-xs">{position.symbol}</TableCell>
              <TableCell>
                <SidePill side={position.side} />
              </TableCell>
              <TableCell className="text-right font-mono text-xs tabular-nums">
                {formatLots(position.lots)}
              </TableCell>
              <TableCell className="text-right font-mono text-xs tabular-nums">
                {formatPrice(position.symbol, position.entry)}
              </TableCell>
              <TableCell className="text-right font-mono text-xs tabular-nums">
                {formatPrice(position.symbol, position.mark)}
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
                <Button
                  type="button"
                  size="xs"
                  variant="outline"
                  onClick={() => flatten(position.id)}
                >
                  Close
                </Button>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
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
