import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export interface WsfOperatorEnv {
  mt5Login: string | null;
  mt5Server: string | null;
  hasMt5Password: boolean;
  mt5Backend: string | null;
  winePrefix: string | null;
  stateFile: string | null;
  bridgeDir: string | null;
  hasMetaApiToken: boolean;
  hasCTraderToken: boolean;
  hasCTraderPassword: boolean;
  email: string | null;
}

const REPO_ROOT = join(homedir(), "Projects/trading/mt5-arch-integration");
const DEFAULT_WSF_PREFIX = join(homedir(), ".mt5-wsf");

/** Live OrderSend is WSF-only. Never follow a leftover Vantage/FP WINEPREFIX. */
export const WSF_ONLY_PREFIX = DEFAULT_WSF_PREFIX;
export const WSF_BRAND_INSTALL = "WSFmarkets MT5 Terminal";
export const WSF_EXPECTED_LOGIN = "149736";
export const WSF_LIVE_CONFIRM = "WSF-149736";
export const WSF_SERVER_NEEDLE = "WSF";

const FILE_CANDIDATES = [
  process.env.WSF_ENV_FILE,
  ".env.local",
  ".env",
  join(process.cwd(), "../../.env"),
  join(REPO_ROOT, ".env"),
  join(process.cwd(), "config/brokers/wsf.env"),
  join(process.cwd(), "../../config/brokers/wsf.env"),
  join(REPO_ROOT, "config/brokers/wsf.env"),
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
      if (path.endsWith(".json")) continue;
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

export function readOperatorEnv(): WsfOperatorEnv {
  const file = fileEnv();
  const email = pick(file, "WSF_DEMO_EMAIL", "WSF_EMAIL", "MT5_EMAIL");
  return {
    mt5Login: pick(file, "WSF_MT5_LOGIN", "MT5_LOGIN"),
    mt5Server: pick(file, "WSF_MT5_SERVER", "MT5_SERVER") || "WSFmarkets-Server",
    hasMt5Password: Boolean(pick(file, "WSF_MT5_PASSWORD", "MT5_PASSWORD")),
    mt5Backend: pick(file, "MT5_BACKEND", "WSF_MT5_BACKEND"),
    winePrefix: pick(file, "WINEPREFIX") || (existsSync(DEFAULT_WSF_PREFIX) ? DEFAULT_WSF_PREFIX : null),
    stateFile: pick(file, "WSF_MT5_STATE_FILE", "MT5_STATE_FILE"),
    bridgeDir: pick(file, "MT5_BRIDGE_DIR", "WSF_MT5_BRIDGE_DIR"),
    hasMetaApiToken: Boolean(pick(file, "METAAPI_TOKEN")),
    hasCTraderToken: Boolean(pick(file, "CTRADER_ACCESS_TOKEN")),
    hasCTraderPassword: Boolean(pick(file, "WSF_DEMO_PASSWORD", "WSF_CTRADER_PASSWORD")),
    email,
  };
}

export function operatorEnvPresent(env: WsfOperatorEnv): boolean {
  return Boolean(env.mt5Login || env.hasMt5Password || env.hasMetaApiToken);
}

export function winePrefixExists(env: WsfOperatorEnv): boolean {
  if (env.winePrefix && existsSync(env.winePrefix)) return true;
  return existsSync(DEFAULT_WSF_PREFIX);
}

export function resolveWsfOnlyPrefix(): string {
  return WSF_ONLY_PREFIX;
}

export function wsfBrandTerminalDir(): string {
  return join(WSF_ONLY_PREFIX, "drive_c", "Program Files", WSF_BRAND_INSTALL);
}
