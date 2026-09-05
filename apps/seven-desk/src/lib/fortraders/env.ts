import { existsSync, readdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import {
  FORTRADERS_EXPECTED_LOGIN,
  FORTRADERS_EXPECTED_SERVER,
} from "@/lib/fortraders/types";

export {
  FORTRADERS_EXPECTED_LOGIN,
  FORTRADERS_EXPECTED_SERVER,
  FORTRADERS_SERVER_NEEDLE,
} from "@/lib/fortraders/types";

/** Official FT Trading tree only. Never FTMO, FP Markets, or FundingPips. */
export const FORTRADERS_BRAND_INSTALL = "FT Trading MT5 Terminal";
export const FORTRADERS_BRAND_INSTALLS = [FORTRADERS_BRAND_INSTALL] as const;
export const FORTRADERS_ONLY_PREFIX = join(homedir(), ".mt5-fortraders");

export interface FortradersOperatorEnv {
  mt5Login: string | null;
  mt5Server: string | null;
  hasMt5Password: boolean;
  winePrefix: string;
  bridgeDir: string | null;
}

const REPO_ROOT = join(homedir(), "Projects/trading/mt5-arch-integration");

const FILE_CANDIDATES = [
  process.env.FORTRADERS_ENV_FILE,
  ".env.local",
  ".env",
  join(process.cwd(), "../../.env"),
  join(REPO_ROOT, ".env"),
  join(REPO_ROOT, "config/brokers/fortraders.env"),
].filter((path): path is string => Boolean(path));

function expandHome(value: string): string {
  const home = homedir();
  return value.replace(/\$\{HOME\}/g, home).replace(/\$HOME/g, home).replace(/^~\//, `${home}/`);
}

function parseEnvText(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const stripped = line.replace(/^export\s+/, "");
    const eq = stripped.indexOf("=");
    if (eq <= 0) continue;
    const key = stripped.slice(0, eq).trim();
    let value = stripped.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (key) out[key] = expandHome(value);
  }
  return out;
}

function fileEnv(): Record<string, string> {
  const merged: Record<string, string> = {};
  for (const path of FILE_CANDIDATES) {
    try {
      if (!path || !existsSync(path)) continue;
      Object.assign(merged, parseEnvText(readFileSync(path, "utf8")));
    } catch {
      // ignore unreadable gitignored files
    }
  }
  return merged;
}

function pick(file: Record<string, string>, ...keys: string[]): string | null {
  for (const key of keys) {
    const fromProcess = process.env[key];
    if (fromProcess && fromProcess.trim()) return expandHome(fromProcess.trim());
    const fromFile = file[key];
    if (fromFile && fromFile.trim()) return fromFile.trim();
  }
  return null;
}

/** Read-only. Never fall back to FTMO/FP Markets/FundingPips `MT5_*` / `WINEPREFIX`. */
export function readFortradersEnv(): FortradersOperatorEnv {
  const file = fileEnv();
  return {
    mt5Login: pick(file, "FORTRADERS_MT5_LOGIN") || FORTRADERS_EXPECTED_LOGIN,
    mt5Server: pick(file, "FORTRADERS_MT5_SERVER") || FORTRADERS_EXPECTED_SERVER,
    hasMt5Password: Boolean(pick(file, "FORTRADERS_MT5_PASSWORD")),
    winePrefix: pick(file, "FORTRADERS_WINEPREFIX") || FORTRADERS_ONLY_PREFIX,
    bridgeDir: pick(file, "FORTRADERS_MT5_BRIDGE_DIR"),
  };
}

export function fortradersBrandTerminalDir(prefix = FORTRADERS_ONLY_PREFIX): string {
  return join(prefix, "drive_c", "Program Files", FORTRADERS_BRAND_INSTALL);
}

function commonBridgeDirs(prefix: string): string[] {
  const users = join(prefix, "drive_c", "users");
  const out: string[] = [];
  if (!existsSync(users)) return out;
  try {
    for (const name of readdirSync(users)) {
      out.push(
        join(
          users,
          name,
          "AppData",
          "Roaming",
          "MetaQuotes",
          "Terminal",
          "Common",
          "Files",
          "mt5_arch"
        )
      );
    }
  } catch {
    return out;
  }
  return out;
}

export function fortradersBridgeCandidates(prefix = FORTRADERS_ONLY_PREFIX): string[] {
  return [
    join(fortradersBrandTerminalDir(prefix), "MQL5", "Files", "mt5_arch"),
    ...commonBridgeDirs(prefix),
  ];
}

export function fortradersBridgeDir(prefix = FORTRADERS_ONLY_PREFIX): string {
  const candidates = fortradersBridgeCandidates(prefix);
  for (const dir of candidates) {
    if (existsSync(join(dir, "account.json")) || existsSync(join(dir, "heartbeat.txt"))) {
      return dir;
    }
  }
  for (const dir of candidates) {
    if (existsSync(dir)) return dir;
  }
  return candidates[0];
}
