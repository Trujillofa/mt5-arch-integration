import type { Side } from "@/lib/types";

export function formatMoney(value: number, currency = "USD"): string {
  const sign = value < 0 ? "-" : "";
  return `${sign}${currency} ${Math.abs(value).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function formatLots(lots: number): string {
  return lots.toFixed(2);
}

export function formatPnl(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "" : "";
  return `${sign}${value.toFixed(2)}`;
}

export function formatPrice(symbol: string, price: number): string {
  if (symbol.includes("JPY")) return price.toFixed(3);
  if (symbol.startsWith("XAU") || symbol === "GOLD") return price.toFixed(2);
  if (symbol.startsWith("NAS") || symbol.startsWith("US") || symbol === "USTEC") {
    return price.toFixed(1);
  }
  return price.toFixed(5);
}

export function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function sideLabel(side: Side): string {
  return side === "buy" ? "Buy" : "Sell";
}

export function compactNumber(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(0)}k`;
  return value.toFixed(0);
}
