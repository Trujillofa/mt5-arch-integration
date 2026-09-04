import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { FTMO_EXPECTED_LOGIN, FTMO_EXPECTED_SERVER } from "@/lib/ftmo/types";

export {
  FTMO_EXPECTED_LOGIN,
  FTMO_EXPECTED_SERVER,
  FTMO_SERVER_NEEDLE,
} from "@/lib/ftmo/types";

/** Official FTMO tree only. Never the generic MetaQuotes folder in this prefix. */
export const FTMO_BRAND_INSTALL = "FTMO Global Markets MT5 Terminal";
export const FTMO_BRAND_INSTALLS = [FTMO_BRAND_INSTALL] as const;
export const FTMO_ONLY_PREFIX = join(homedir(), ".mt5-ftmo");

export interface FtmoOperatorEnv {
  mt5Login: string | null;
  mt5Server: string | null;
  hasMt5Password: boolean;
  winePrefix: string;
  bridgeDir: string | null;
}

const REPO_ROOT = join(homedir(), "Projects/trading/mt5-arch-integration");

const FILE_CANDIDATES = [
  process.env.FTMO_ENV_FILE,
  ".env.local",
  ".env",
  join(process.cwd(), "../../.env"),
  join(REPO_ROOT, ".env"),
  join(REPO_ROOT, "config/brokers/ftmo.env"),
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
export function readFtmoEnv(): FtmoOperatorEnv {
  const file = fileEnv();
  return {
    mt5Login: pick(file, "FTMO_MT5_LOGIN") || FTMO_EXPECTED_LOGIN,
    mt5Server: pick(file, "FTMO_MT5_SERVER") || FTMO_EXPECTED_SERVER,
    hasMt5Password: Boolean(pick(file, "FTMO_MT5_PASSWORD")),
    winePrefix: pick(file, "FTMO_WINEPREFIX") || FTMO_ONLY_PREFIX,
    bridgeDir: pick(file, "FTMO_MT5_BRIDGE_DIR"),
  };
}

export function ftmoBrandTerminalDir(prefix = FTMO_ONLY_PREFIX): string {
  return join(prefix, "drive_c", "Program Files", FTMO_BRAND_INSTALL);
}

export function ftmoBridgeCandidates(prefix = FTMO_ONLY_PREFIX): string[] {
  return [join(ftmoBrandTerminalDir(prefix), "MQL5", "Files", "mt5_arch")];
}

export function ftmoBridgeDir(prefix = FTMO_ONLY_PREFIX): string {
  const candidates = ftmoBridgeCandidates(prefix);
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
