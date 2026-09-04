import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import {
  ALPHACAPITAL_EXPECTED_LOGIN,
  ALPHACAPITAL_EXPECTED_SERVER,
} from "@/lib/alphacapital/types";

export {
  ALPHACAPITAL_EXPECTED_LOGIN,
  ALPHACAPITAL_EXPECTED_SERVER,
  ALPHACAPITAL_SERVER_NEEDLE,
} from "@/lib/alphacapital/types";

/** Official ACG Markets tree only. Never the generic MetaQuotes folder in this prefix. */
export const ALPHACAPITAL_BRAND_INSTALL = "ACG Markets MT5 Terminal";
export const ALPHACAPITAL_BRAND_INSTALLS = [ALPHACAPITAL_BRAND_INSTALL] as const;
export const ALPHACAPITAL_ONLY_PREFIX = join(homedir(), ".mt5-alphacapital");

export interface AlphaCapitalOperatorEnv {
  mt5Login: string | null;
  mt5Server: string | null;
  hasMt5Password: boolean;
  winePrefix: string;
  bridgeDir: string | null;
}

const REPO_ROOT = join(homedir(), "Projects/trading/mt5-arch-integration");

const FILE_CANDIDATES = [
  process.env.ALPHACAPITAL_ENV_FILE,
  process.env.ALPHA_ENV_FILE,
  ".env.local",
  ".env",
  join(process.cwd(), "../../.env"),
  join(REPO_ROOT, ".env"),
  join(REPO_ROOT, "config/brokers/alphacapital.env"),
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

/** Read-only. Never fall back to WSF `MT5_*` / `WINEPREFIX`. */
export function readAlphaCapitalEnv(): AlphaCapitalOperatorEnv {
  const file = fileEnv();
  return {
    mt5Login: pick(file, "ALPHA_MT5_LOGIN", "ACG_MT5_LOGIN") || ALPHACAPITAL_EXPECTED_LOGIN,
    mt5Server: pick(file, "ALPHA_MT5_SERVER", "ACG_MT5_SERVER") || ALPHACAPITAL_EXPECTED_SERVER,
    hasMt5Password: Boolean(pick(file, "ALPHA_MT5_PASSWORD", "ACG_MT5_PASSWORD")),
    winePrefix: pick(file, "ALPHA_WINEPREFIX", "ACG_WINEPREFIX") || ALPHACAPITAL_ONLY_PREFIX,
    bridgeDir: pick(file, "ALPHA_MT5_BRIDGE_DIR", "ACG_MT5_BRIDGE_DIR"),
  };
}

export function alphacapitalBrandTerminalDir(prefix = ALPHACAPITAL_ONLY_PREFIX): string {
  return join(prefix, "drive_c", "Program Files", ALPHACAPITAL_BRAND_INSTALL);
}

export function alphacapitalBridgeCandidates(prefix = ALPHACAPITAL_ONLY_PREFIX): string[] {
  return [join(alphacapitalBrandTerminalDir(prefix), "MQL5", "Files", "mt5_arch")];
}

export function alphacapitalBridgeDir(prefix = ALPHACAPITAL_ONLY_PREFIX): string {
  const candidates = alphacapitalBridgeCandidates(prefix);
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
