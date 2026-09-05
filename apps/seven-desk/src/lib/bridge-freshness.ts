import { existsSync, readdirSync, readFileSync, realpathSync, statSync } from "node:fs";
import { join } from "node:path";

/** Matches `mt5_arch.file_bridge.DEFAULT_MAX_AGE_SECONDS` / Settings default. */
export const DEFAULT_BRIDGE_MAX_AGE_SECONDS = 15;

export function bridgeMaxAgeSeconds(env: NodeJS.ProcessEnv = process.env): number {
  const raw = env.MT5_BRIDGE_MAX_AGE;
  if (raw == null || String(raw).trim() === "") return DEFAULT_BRIDGE_MAX_AGE_SECONDS;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_BRIDGE_MAX_AGE_SECONDS;
}

export interface BridgeFreshness {
  fileBridgePresent: boolean;
  heartbeatPresent: boolean;
  heartbeatAgeSeconds: number | null;
  heartbeatFresh: boolean;
  terminalRunning: boolean;
  terminalChecked: boolean;
}

export type FileBridgeConnectionStatus =
  | "connected"
  | "disconnected"
  | "missing_wine"
  | "auth_failed"
  | "password_missing"
  | "no_credentials"
  | "wrong_account";

function isFile(path: string): boolean {
  try {
    return existsSync(path) && statSync(path).isFile();
  } catch {
    return false;
  }
}

function real(path: string): string {
  try {
    return realpathSync(path);
  } catch {
    return path;
  }
}

/** Same-user /proc scan used by the live-order runner. Server-only. */
export function prefixHasTerminal64(winePrefix: string): boolean {
  const want = real(winePrefix);
  let names: string[] = [];
  try {
    names = readdirSync("/proc").filter((name) => /^\d+$/.test(name));
  } catch {
    return false;
  }
  for (const pid of names) {
    try {
      const cmd = readFileSync(`/proc/${pid}/cmdline`).toString("utf8").replace(/\0/g, " ");
      if (!cmd.includes("terminal64.exe") || cmd.includes("bash")) continue;
      let got = "";
      try {
        const environ = readFileSync(`/proc/${pid}/environ`).toString("utf8");
        for (const part of environ.split("\0")) {
          if (part.startsWith("WINEPREFIX=")) {
            got = real(part.slice("WINEPREFIX=".length));
            break;
          }
        }
      } catch {
        got = "";
      }
      if (got === want) return true;
    } catch {
      continue;
    }
  }
  return false;
}

export function inspectBridgeFreshness(input: {
  bridgeDirs: string[];
  winePrefix?: string | null;
  nowMs?: number;
  maxAgeSeconds?: number;
}): BridgeFreshness {
  const nowMs = input.nowMs ?? Date.now();
  const maxAge = input.maxAgeSeconds ?? bridgeMaxAgeSeconds();
  let fileBridgePresent = false;
  let heartbeatPresent = false;
  let heartbeatAgeSeconds: number | null = null;

  for (const dir of input.bridgeDirs) {
    const account = join(dir, "account.json");
    const heartbeat = join(dir, "heartbeat.txt");
    if (isFile(account) || isFile(heartbeat)) fileBridgePresent = true;
    if (!isFile(heartbeat)) continue;
    heartbeatPresent = true;
    const age = (nowMs - statSync(heartbeat).mtimeMs) / 1000;
    if (heartbeatAgeSeconds == null || age < heartbeatAgeSeconds) {
      heartbeatAgeSeconds = age;
    }
  }

  const heartbeatFresh =
    heartbeatPresent && heartbeatAgeSeconds != null && heartbeatAgeSeconds <= maxAge;
  const winePrefix = input.winePrefix;
  const terminalChecked = Boolean(winePrefix);
  const terminalRunning = winePrefix ? prefixHasTerminal64(winePrefix) : false;

  return {
    fileBridgePresent,
    heartbeatPresent,
    heartbeatAgeSeconds,
    heartbeatFresh,
    terminalRunning,
    terminalChecked,
  };
}

/** Hours-old account.json is not a live session. */
export function canReportConnected(freshness: BridgeFreshness): boolean {
  if (!freshness.heartbeatFresh) return false;
  if (freshness.terminalChecked && !freshness.terminalRunning) return false;
  return true;
}

export function freshnessRejectNote(
  freshness: BridgeFreshness,
  maxAge = bridgeMaxAgeSeconds(),
): string | null {
  if (canReportConnected(freshness)) return null;
  if (!freshness.heartbeatFresh) {
    if (freshness.heartbeatAgeSeconds == null) {
      return `Heartbeat missing — not treating a leftover account.json as connected (MT5_BRIDGE_MAX_AGE=${maxAge}s).`;
    }
    return `Heartbeat age ${Math.round(freshness.heartbeatAgeSeconds)}s exceeds MT5_BRIDGE_MAX_AGE=${maxAge}s — not treating a leftover account.json as connected.`;
  }
  return "terminal64 is not running for this prefix — not treating a leftover account.json as connected.";
}

export function deriveFileBridgeConnectionStatus(input: {
  login: string | null | undefined;
  expectedLogin: string;
  snapshotLive: boolean;
  terminalConnected?: boolean | null;
  winePrefixPresent: boolean;
  fileBridgePresent: boolean;
  freshness: BridgeFreshness;
  hasPassword: boolean;
  usedOperator: boolean;
}): FileBridgeConnectionStatus {
  const login = input.login ?? null;
  if (login && login !== input.expectedLogin) return "wrong_account";
  if (input.snapshotLive && login === input.expectedLogin) {
    if (!canReportConnected(input.freshness)) return "disconnected";
    if (input.terminalConnected === false) return "disconnected";
    return "connected";
  }
  // Title-only expected login + bridge files: trade server offline (weekend FX),
  // not a bad password. Auth-failed made Fetch look broken.
  if (login === input.expectedLogin && input.fileBridgePresent) return "disconnected";
  if (!input.usedOperator) return "no_credentials";
  if (!input.hasPassword) return "password_missing";
  if (!input.winePrefixPresent || !input.fileBridgePresent) return "missing_wine";
  return "auth_failed";
}
