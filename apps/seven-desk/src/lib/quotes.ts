import type { PaperQuote, Side } from "@/lib/types";

export const MASTER_SYMBOLS = [
  "EURUSD",
  "GBPUSD",
  "USDJPY",
  "XAUUSD",
  "NAS100",
  "US30",
] as const;

export type MasterSymbol = (typeof MASTER_SYMBOLS)[number];

export const SEED_QUOTES: PaperQuote[] = [
  { symbol: "EURUSD", bid: 1.08512, ask: 1.08518, pip: 0.0001 },
  { symbol: "GBPUSD", bid: 1.27136, ask: 1.27144, pip: 0.0001 },
  { symbol: "USDJPY", bid: 149.812, ask: 149.818, pip: 0.01 },
  { symbol: "XAUUSD", bid: 2348.42, ask: 2348.62, pip: 0.1 },
  { symbol: "GOLD", bid: 2348.40, ask: 2348.64, pip: 0.1 },
  { symbol: "NAS100", bid: 19838.5, ask: 19841.0, pip: 1 },
  { symbol: "USTEC", bid: 19838.0, ask: 19841.5, pip: 1 },
  { symbol: "US30", bid: 39118.0, ask: 39122.0, pip: 1 },
];

export function quoteBySymbol(
  quotes: PaperQuote[],
  symbol: string
): PaperQuote | undefined {
  return quotes.find((quote) => quote.symbol === symbol);
}

export function midPrice(quote: PaperQuote): number {
  return (quote.bid + quote.ask) / 2;
}

export function markForSide(quote: PaperQuote, side: Side): number {
  return side === "buy" ? quote.bid : quote.ask;
}

export function pipDistance(quote: PaperQuote, from: number, to: number): number {
  return Math.abs(to - from) / quote.pip;
}

export function floatingPnl(
  side: Side,
  lots: number,
  entry: number,
  mark: number,
  symbol: string
): number {
  const direction = side === "buy" ? 1 : -1;
  const contract = contractSize(symbol);
  return direction * (mark - entry) * lots * contract;
}

function contractSize(symbol: string): number {
  if (symbol.includes("JPY")) return 1000;
  if (symbol.startsWith("XAU") || symbol === "GOLD") return 100;
  if (symbol.startsWith("NAS") || symbol === "USTEC") return 1;
  if (symbol.startsWith("US")) return 1;
  return 100_000;
}

export function nudgeQuotes(quotes: PaperQuote[], now = Date.now()): PaperQuote[] {
  return quotes.map((quote, index) => {
    const wave = Math.sin(now / 1400 + index * 1.7) * quote.pip * 1.4;
    const noise = ((now / 90 + index * 13) % 7) * 0.08 * quote.pip;
    const delta = wave + (index % 2 === 0 ? noise : -noise);
    const spread = quote.ask - quote.bid;
    const mid = midPrice(quote) + delta * 0.15;
    return {
      ...quote,
      bid: roundToPip(mid - spread / 2, quote.pip),
      ask: roundToPip(mid + spread / 2, quote.pip),
    };
  });
}

function roundToPip(value: number, pip: number): number {
  return Math.round(value / pip) * pip;
}
