import { existsSync, readdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import {
  FUNDINGPIPS_EXPECTED_LOGIN,
  FUNDINGPIPS_EXPECTED_SERVER,
} from "@/lib/fundingpips/types";

export {
  FUNDINGPIPS_EXPECTED_LOGIN,
  FUNDINGPIPS_EXPECTED_SERVER,
  FUNDINGPIPS_SERVER_NEEDLE,
} from "@/lib/fundingpips/types";

/** Official FundingPips tree only. Never the generic MetaQuotes folder, never FP Markets. */
export const FUNDINGPIPS_BRAND_INSTALL = "FundingPips 2 MT5 Terminal";
export const FUNDINGPIPS_BRAND_INSTALLS = [FUNDINGPIPS_BRAND_INSTALL] as const;
export const FUNDINGPIPS_ONLY_PREFIX = join(homedir(), ".mt5-fundingpips");

export interface FundingPipsOperatorEnv {
  mt5Login: string | null;
  mt5Server: string | null;
  hasMt5Password: boolean;
  winePrefix: string;
  bridgeDir: string | null;
}

const REPO_ROOT = join(homedir(), "Projects/trading/mt5-arch-integration");

const FILE_CANDIDATES = [
  process.env.FUNDINGPIPS_ENV_FILE,
  ".env.local",
  ".env",
  join(process.cwd(), "../../.env"),
  join(REPO_ROOT, ".env"),
  join(REPO_ROOT, "config/brokers/fundingpips.env"),
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

/** Read-only. Never fall back to WSF/FP Markets `MT5_*` / `WINEPREFIX`. */
export function readFundingPipsEnv(): FundingPipsOperatorEnv {
  const file = fileEnv();
  return {
    mt5Login: pick(file, "FUNDINGPIPS_MT5_LOGIN") || FUNDINGPIPS_EXPECTED_LOGIN,
    mt5Server: pick(file, "FUNDINGPIPS_MT5_SERVER") || FUNDINGPIPS_EXPECTED_SERVER,
    hasMt5Password: Boolean(pick(file, "FUNDINGPIPS_MT5_PASSWORD")),
    winePrefix: pick(file, "FUNDINGPIPS_WINEPREFIX") || FUNDINGPIPS_ONLY_PREFIX,
    bridgeDir: pick(file, "FUNDINGPIPS_MT5_BRIDGE_DIR"),
  };
}

export function fundingpipsBrandTerminalDir(prefix = FUNDINGPIPS_ONLY_PREFIX): string {
  return join(prefix, "drive_c", "Program Files", FUNDINGPIPS_BRAND_INSTALL);
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

export function fundingpipsBridgeCandidates(prefix = FUNDINGPIPS_ONLY_PREFIX): string[] {
  return [
    join(fundingpipsBrandTerminalDir(prefix), "MQL5", "Files", "mt5_arch"),
    ...commonBridgeDirs(prefix),
  ];
}

export function fundingpipsBridgeDir(prefix = FUNDINGPIPS_ONLY_PREFIX): string {
  const candidates = fundingpipsBridgeCandidates(prefix);
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
