"use client";

import { CopyStatusPill, SidePill } from "@/components/desk/status-pills";
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
import { formatLots, formatPrice, formatTime } from "@/lib/format";

export function BlotterTable() {
  const { state } = useDesk();
  const rows = state.blotter;

  if (rows.length === 0) {
    return (
      <div className="px-4 py-10 text-center">
        <p className="text-sm font-medium">No fills yet</p>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          Place a master trade to see the paper book and every child order —
          queued, copied, skipped, or rejected — with the reason.
        </p>
      </div>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Time</TableHead>
          <TableHead>Account</TableHead>
          <TableHead>Role</TableHead>
          <TableHead>Symbol</TableHead>
          <TableHead>Side</TableHead>
          <TableHead className="text-right">Lots</TableHead>
          <TableHead className="text-right">Fill</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Reason</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((event) => {
          const account = state.accounts.find((row) => row.id === event.accountId);
          const firm = account ? FIRM_BY_ID[account.firmId].name : "—";
          return (
            <TableRow key={event.id}>
              <TableCell className="font-mono text-xs text-muted-foreground">
                {formatTime(event.createdAt)}
              </TableCell>
              <TableCell>
                <div className="leading-tight">
                  <p className="text-sm">{firm}</p>
                  <p className="font-mono text-[11px] text-muted-foreground">
                    {account?.login ?? event.accountId}
                  </p>
                </div>
              </TableCell>
              <TableCell className="font-mono text-[11px] tracking-wide uppercase text-muted-foreground">
                {event.role}
              </TableCell>
              <TableCell className="font-mono text-xs">{event.symbol}</TableCell>
              <TableCell>
                <SidePill side={event.side} />
              </TableCell>
              <TableCell className="text-right font-mono text-xs tabular-nums">
                {formatLots(event.lots)}
              </TableCell>
              <TableCell className="text-right font-mono text-xs tabular-nums">
                {event.fillPrice != null
                  ? formatPrice(event.symbol, event.fillPrice)
                  : "—"}
              </TableCell>
              <TableCell>
                <CopyStatusPill status={event.status} />
              </TableCell>
              <TableCell className="max-w-[240px] text-xs text-muted-foreground">
                {event.reason ?? "—"}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
