/** Client-safe pending-order parse. Do not import server env modules here. */

export interface BridgePendingOrder {
  ticket: number;
  symbol: string;
  type: string;
  side: string;
  volume: number | null;
  price: number | null;
  sl: number | null;
  tp: number | null;
  status: string;
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value.replace(/,/g, ""));
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function asString(value: unknown): string {
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return "";
}

/** Parse EA orders.json. History-shaped objects without an orders array yield []. */
export function parsePendingOrders(raw: unknown): BridgePendingOrder[] {
  if (raw == null) return [];
  const list = Array.isArray(raw)
    ? raw
    : raw && typeof raw === "object" && Array.isArray((raw as { orders?: unknown }).orders)
      ? (raw as { orders: unknown[] }).orders
      : null;
  if (!list) return [];
  const out: BridgePendingOrder[] = [];
  for (const row of list) {
    if (!row || typeof row !== "object") continue;
    const item = row as Record<string, unknown>;
    const ticket = asNumber(item.ticket);
    if (ticket == null || ticket <= 0) continue;
    const type = asString(item.type);
    const side = asString(item.side) || (type.startsWith("sell") ? "sell" : "buy");
    out.push({
      ticket,
      symbol: asString(item.symbol) || "unknown",
      type: type || "pending",
      side,
      volume: asNumber(item.volume ?? item.lots),
      price: asNumber(item.price_open ?? item.price ?? item.open_price),
      sl: asNumber(item.stop_loss ?? item.sl),
      tp: asNumber(item.take_profit ?? item.tp),
      status: asString(item.status) || "pending",
    });
  }
  return out;
}

export function pendingOrderKind(type: string): "limit" | "stop" | "pending" {
  if (type.includes("limit")) return "limit";
  if (type.includes("stop")) return "stop";
  return "pending";
}
