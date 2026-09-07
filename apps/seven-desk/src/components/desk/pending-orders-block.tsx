import {
  pendingOrderKind,
  type BridgePendingOrder,
} from "@/lib/bridge-orders";

export function PendingOrdersBlock({ orders }: { orders: BridgePendingOrder[] }) {
  if (orders.length === 0) {
    return (
      <p className="rounded-md bg-background/40 px-2 py-1.5 text-muted-foreground">
        Open limits/stops:{" "}
        <span className="font-mono text-foreground">0</span>
        {" · "}
        none in orders.json (OrdersTotal). PositionsTotal is a different dump.
      </p>
    );
  }
  return (
    <div className="space-y-1.5 rounded-md bg-background/40 px-2 py-1.5 text-muted-foreground">
      <p>
        Open limits/stops:{" "}
        <span className="font-mono text-foreground">{orders.length}</span>
      </p>
      <ul className="space-y-1">
        {orders.slice(0, 12).map((row) => (
          <li key={row.ticket} className="font-mono">
            {pendingOrderKind(row.type)} #{row.ticket} {row.side} {row.symbol}{" "}
            vol {row.volume ?? "—"} @ {row.price ?? "—"}
          </li>
        ))}
      </ul>
    </div>
  );
}
