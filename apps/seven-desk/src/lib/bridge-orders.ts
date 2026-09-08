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

export interface BridgeOpenPosition {
  ticket: number;
  symbol: string;
  side: string;
  volume: number | null;
  price: number | null;
  sl: number | null;
  tp: number | null;
  profit: number | null;
  magic: number | null;
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

/** Parse EA positions.json. PositionsTotal snapshot; leftover vs desk uses magic. */
export function parseOpenPositions(raw: unknown): BridgeOpenPosition[] {
  if (raw == null) return [];
  const list = Array.isArray(raw)
    ? raw
    : raw && typeof raw === "object" && Array.isArray((raw as { positions?: unknown }).positions)
      ? (raw as { positions: unknown[] }).positions
      : null;
  if (!list) return [];
  const out: BridgeOpenPosition[] = [];
  for (const row of list) {
    if (!row || typeof row !== "object") continue;
    const item = row as Record<string, unknown>;
    const ticket = asNumber(item.ticket);
    if (ticket == null || ticket <= 0) continue;
    const side = asString(item.side ?? item.type).toLowerCase();
    out.push({
      ticket,
      symbol: asString(item.symbol) || "unknown",
      side: side === "sell" ? "sell" : "buy",
      volume: asNumber(item.volume ?? item.lots),
      price: asNumber(item.open_price ?? item.entry ?? item.priceOpen ?? item.price),
      sl: asNumber(item.stop_loss ?? item.sl),
      tp: asNumber(item.take_profit ?? item.tp),
      profit: asNumber(item.profit ?? item.pnl),
      magic: asNumber(item.magic),
      status: asString(item.status) || "open",
    });
  }
  return out;
}

export function toBridgeOpenPositions(
  rows: Array<{
    ticket?: number | null;
    symbol?: string;
    side?: string;
    volume?: number | null;
    entry?: number | null;
    sl?: number | null;
    tp?: number | null;
    pnl?: number | null;
    magic?: number | null;
  }>
): BridgeOpenPosition[] {
  const out: BridgeOpenPosition[] = [];
  for (const row of rows) {
    const ticket = row.ticket;
    if (ticket == null || ticket <= 0) continue;
    out.push({
      ticket,
      symbol: row.symbol || "unknown",
      side: row.side === "sell" ? "sell" : "buy",
      volume: row.volume ?? null,
      price: row.entry ?? null,
      sl: row.sl ?? null,
      tp: row.tp ?? null,
      profit: row.pnl ?? null,
      magic: row.magic ?? null,
      status: "open",
    });
  }
  return out;
}

export function pendingOrderKind(type: string): "limit" | "stop" | "pending" {
  if (type.includes("limit")) return "limit";
  if (type.includes("stop")) return "stop";
  return "pending";
}
