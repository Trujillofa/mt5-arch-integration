import { existsSync, readFileSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { WSF_EXPECTED_LOGIN } from "@/lib/wsf/constants";
import type { WsfDealRow, WsfFetchedAccount, WsfPositionRow } from "@/lib/wsf/types";
import type { WsfOperatorEnv } from "@/lib/wsf/env";

export interface Mt5FileSnapshot {
  book: WsfFetchedAccount | null;
  positions: WsfPositionRow[];
  deals: WsfDealRow[];
  note: string;
}

const BRAND_DIRS = ["WSFmarkets MT5 Terminal"];

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value.replace(/,/g, ""));
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function asString(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number") return String(value);
  return null;
}

function isFile(path: string): boolean {
  try {
    return existsSync(path) && statSync(path).isFile();
  } catch {
    return false;
  }
}

function isDir(path: string): boolean {
  try {
    return existsSync(path) && statSync(path).isDirectory();
  } catch {
    return false;
  }
}

function isWsfPrefix(prefix: string): boolean {
  return prefix.includes(".mt5-wsf");
}

function bridgeDirs(env: WsfOperatorEnv): string[] {
  const dirs: string[] = [];
  if (env.bridgeDir && isWsfPrefix(env.bridgeDir)) dirs.push(env.bridgeDir);
  const prefixes = [env.winePrefix, join(homedir(), ".mt5-wsf")].filter(
    (path): path is string => typeof path === "string" && isWsfPrefix(path)
  );
  for (const prefix of prefixes) {
    for (const brand of BRAND_DIRS) {
      dirs.push(join(prefix, "drive_c", "Program Files", brand, "MQL5", "Files", "mt5_arch"));
    }
  }
  return [...new Set(dirs)];
}

function snapshotFiles(env: WsfOperatorEnv): string[] {
  return [
    env.stateFile,
    process.env.WSF_MT5_STATE_FILE,
    ...bridgeDirs(env).map((dir) => join(dir, "account.json")),
  ].filter((path): path is string => Boolean(path));
}

function parseBook(
  raw: Record<string, unknown>,
  env: WsfOperatorEnv
): WsfFetchedAccount | null {
  const login = asString(raw.login ?? raw.account ?? raw.mt5Login) || env.mt5Login;
  if (!login) return null;
  const server =
    asString(raw.server ?? raw.broker ?? raw.company) || env.mt5Server || "WSFmarkets-Server";
  const balance = asNumber(raw.balance);
  const leverage = raw.leverage;
  return {
    source: "mt5-env",
    kind: "personal-env",
    broker: server,
    accountId: login,
    login,
    name: asString(raw.name ?? raw.comment) || `WSF MT5 ${login}`,
    environment: "unknown",
    accountType: asString(raw.accountType ?? raw.trade_mode),
    balance,
    equity: asNumber(raw.equity) ?? balance,
    currency: asString(raw.currency) || "USD",
    leverage:
      typeof leverage === "number"
        ? `1:${leverage}`
        : asString(leverage),
    plantIsWsf: true,
  };
}

function parsePositions(raw: unknown, login: string): WsfPositionRow[] {
  const list = Array.isArray(raw)
    ? raw
    : raw && typeof raw === "object" && Array.isArray((raw as { positions?: unknown }).positions)
      ? (raw as { positions: unknown[] }).positions
      : [];
  return list.map((row) => {
    const item = row as Record<string, unknown>;
    return {
      accountLogin: login,
      symbol: asString(item.symbol) || "unknown",
      side: asString(item.side ?? item.type) || "unknown",
      volume: asNumber(item.volume ?? item.lots),
      entry: asNumber(item.entry ?? item.open_price ?? item.priceOpen),
      pnl: asNumber(item.pnl ?? item.profit),
    };
  });
}

function parseDealsCsv(text: string, login: string): WsfDealRow[] {
  const lines = text.split(/\r?\n/).filter((line) => line.trim());
  if (lines.length < 2) return [];
  const header = lines[0].split(",").map((cell) => cell.trim());
  const symbolIdx = header.indexOf("symbol");
  const typeIdx = header.indexOf("type");
  const volumeIdx = header.indexOf("volume");
  const priceIdx = header.indexOf("price");
  const timeIdx = header.indexOf("time");
  return lines.slice(1, 21).map((line) => {
    const cols = line.split(",");
    return {
      accountLogin: login,
      symbol: cols[symbolIdx] || "unknown",
      side: cols[typeIdx] || "unknown",
      volume: asNumber(cols[volumeIdx]),
      price: asNumber(cols[priceIdx]),
      time: cols[timeIdx] || null,
    };
  });
}

export function readMt5FileBackend(env: WsfOperatorEnv): Mt5FileSnapshot {
  if (env.mt5Backend && env.mt5Backend !== "file") {
    return {
      book: null,
      positions: [],
      deals: [],
      note: `MT5_BACKEND=${env.mt5Backend} is not a file snapshot — skipped.`,
    };
  }

  let found = 0;
  for (const path of snapshotFiles(env)) {
    if (!isFile(path)) continue;
    found += 1;
    try {
      const raw = JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
      const book = parseBook(raw, env);
      const login = book?.login || env.mt5Login || "unknown";
      if (login !== WSF_EXPECTED_LOGIN) continue;
      const dir = path.endsWith("account.json") ? path.slice(0, -"account.json".length) : "";
      let positions = parsePositions(raw.positions, login);
      let deals: WsfDealRow[] = [];
      if (dir && isFile(join(dir, "positions.json"))) {
        positions = parsePositions(
          JSON.parse(readFileSync(join(dir, "positions.json"), "utf8")),
          login
        );
      }
      const dealsCsv = dir ? join(dir, "deals_export.csv") : "";
      if (dealsCsv && isFile(dealsCsv) && isFile(join(dir, "dump_deals.done"))) {
        deals = parseDealsCsv(readFileSync(dealsCsv, "utf8"), login);
      }
      if (book || positions.length || deals.length) {
        return {
          book,
          positions,
          deals,
          note: `Read Mt5ArchBridge snapshot (${positions.length} position(s), ${deals.length} deal(s)). Path not printed.`,
        };
      }
    } catch {
      continue;
    }
  }

  const anyBridge = bridgeDirs(env).some((dir) => isDir(dir));
  return {
    book: null,
    positions: [],
    deals: [],
    note: env.mt5Backend === "file"
      ? anyBridge
        ? "MT5_BACKEND=file: found a Wine mt5_arch directory but no readable account.json (terminal/EA not writing on this host)."
        : `MT5_BACKEND=file but no Mt5ArchBridge snapshot on this host (${found} candidate file(s)). Use ~/.mt5-wsf + scripts/16-use-broker.sh wsf.`
      : "No MT5 file-backend snapshot configured.",
  };
}
