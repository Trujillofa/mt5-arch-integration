import { existsSync, readFileSync, statSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { homedir } from "node:os";
import { join } from "node:path";
import {
  FUNDEDNEXT_EXPECTED_LOGIN,
  FUNDEDNEXT_EXPECTED_SERVER,
  FUNDEDNEXT_SERVER_NEEDLE,
  fundednextBridgeCandidates,
  fundednextBridgeDir,
  readFundedNextEnv,
  type FundedNextOperatorEnv,
} from "@/lib/fundednext/env";
import type { FundedNextConnectionStatus, FundedNextLiveReport } from "@/lib/fundednext/types";

interface Snapshot {
  login: string | null;
  server: string | null;
  balance: number | null;
  equity: number | null;
  currency: string | null;
  leverage: string | null;
  name: string | null;
  terminalConnected: boolean | null;
}

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

function asBool(value: unknown): boolean | null {
  if (typeof value === "boolean") return value;
  if (value === "true" || value === 1 || value === "1") return true;
  if (value === "false" || value === 0 || value === "0") return false;
  return null;
}

function snapshotIsLive(snapshot: Snapshot | null): boolean {
  if (!snapshot?.login) return false;
  if (snapshot.terminalConnected === true) return true;
  if (snapshot.currency) return true;
  if (snapshot.leverage && snapshot.leverage !== "1:0" && snapshot.leverage !== "0") {
    return true;
  }
  return snapshot.balance != null && snapshot.balance !== 0;
}

function isFile(path: string): boolean {
  try {
    return existsSync(path) && statSync(path).isFile();
  } catch {
    return false;
  }
}

function readAccountJson(path: string): Snapshot | null {
  if (!isFile(path)) return null;
  try {
    const raw = JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
    const login = asString(raw.login ?? raw.account ?? raw.mt5Login);
    return {
      login,
      server: asString(raw.server ?? raw.broker ?? raw.company),
      balance: asNumber(raw.balance),
      equity: asNumber(raw.equity) ?? asNumber(raw.balance),
      currency: asString(raw.currency),
      leverage:
        typeof raw.leverage === "number"
          ? `1:${raw.leverage}`
          : asString(raw.leverage),
      name: asString(raw.name ?? raw.comment),
      terminalConnected: asBool(raw.terminal_connected),
    };
  } catch {
    return null;
  }
}

function probeMt5ArchCli(env: FundedNextOperatorEnv, bridgeDir: string): Snapshot | null {
  const root =
    process.env.MT5_ARCH_ROOT ||
    join(homedir(), "Projects/trading/mt5-arch-integration");
  if (!existsSync(join(root, "pyproject.toml"))) return null;
  const uv = existsSync(join(homedir(), ".local/bin/uv"))
    ? join(homedir(), ".local/bin/uv")
    : "uv";
  const result = spawnSync(uv, ["run", "mt5-arch", "account", "--json"], {
    cwd: root,
    encoding: "utf8",
    timeout: 12000,
    env: {
      ...process.env,
      WINEPREFIX: env.winePrefix,
      MT5_BACKEND: "file",
      MT5_LOGIN: env.mt5Login || FUNDEDNEXT_EXPECTED_LOGIN,
      MT5_SERVER: env.mt5Server || FUNDEDNEXT_EXPECTED_SERVER,
      MT5_BRIDGE_DIR: bridgeDir,
      MT5_PASSWORD: "",
    },
  });
  if (result.status !== 0 || !result.stdout?.trim()) return null;
  try {
    const parsed = JSON.parse(result.stdout.trim()) as Record<string, unknown>;
    return {
      login: asString(parsed.login),
      server: asString(parsed.server),
      balance: asNumber(parsed.balance),
      equity: asNumber(parsed.equity) ?? asNumber(parsed.balance),
      currency: asString(parsed.currency),
      leverage:
        typeof parsed.leverage === "number"
          ? `1:${parsed.leverage}`
          : asString(parsed.leverage),
      name: asString(parsed.name),
      terminalConnected: asBool(parsed.terminal_connected ?? parsed.connected),
    };
  } catch {
    return null;
  }
}

function deriveStatus(input: {
  snapshot: Snapshot | null;
  winePrefixPresent: boolean;
  fileBridgePresent: boolean;
  hasPassword: boolean;
  usedOperator: boolean;
}): FundedNextConnectionStatus {
  const login = input.snapshot?.login;
  if (login && login !== FUNDEDNEXT_EXPECTED_LOGIN) return "wrong_account";
  if (snapshotIsLive(input.snapshot) && login === FUNDEDNEXT_EXPECTED_LOGIN) {
    return "connected";
  }
  if (!input.usedOperator) return "no_credentials";
  if (!input.hasPassword) return "password_missing";
  if (!input.winePrefixPresent || !input.fileBridgePresent) return "missing_wine";
  return "auth_failed";
}

export function probeFundedNextLive(): FundedNextLiveReport {
  const env = readFundedNextEnv();
  const usedOperator = Boolean(env.mt5Login || env.hasMt5Password);
  const winePrefixPresent = existsSync(env.winePrefix);
  const bridgeDirs = env.bridgeDir
    ? [env.bridgeDir]
    : fundednextBridgeCandidates(env.winePrefix);
  const preferredBridge = env.bridgeDir || fundednextBridgeDir(env.winePrefix);
  const fileBridgePresent = bridgeDirs.some(
    (dir) => isFile(join(dir, "account.json")) || isFile(join(dir, "heartbeat.txt")),
  );
  const notes: string[] = [];

  let snapshot: Snapshot | null = null;
  for (const dir of bridgeDirs) {
    const candidate = readAccountJson(join(dir, "account.json"));
    if (!candidate?.login) continue;
    snapshot = candidate;
    notes.push("Read Mt5ArchBridge account.json (path not printed).");
    if (snapshotIsLive(candidate)) break;
  }
  if (snapshot?.login) {
    if (!snapshotIsLive(snapshot)) {
      notes.push(
        "Snapshot is title-only (empty currency/leverage, not trade-authorized)."
      );
    }
  } else {
    notes.push("No readable FundedNext account.json yet.");
    snapshot = probeMt5ArchCli(env, preferredBridge);
    if (snapshot?.login) notes.push("mt5-arch account --json succeeded under the FundedNext prefix.");
  }

  if (snapshot?.login && snapshot.login !== FUNDEDNEXT_EXPECTED_LOGIN) {
    notes.push(
      `Refusing snapshot login ${snapshot.login} — expected ${FUNDEDNEXT_EXPECTED_LOGIN}.`
    );
    snapshot = null;
  }
  if (
    snapshot?.server &&
    !snapshot.server.toLowerCase().includes(FUNDEDNEXT_SERVER_NEEDLE.toLowerCase())
  ) {
    notes.push(`Refusing snapshot server ${snapshot.server} — not a FundedNext server.`);
    snapshot = null;
  }

  const liveBalance = snapshotIsLive(snapshot);
  const connectionStatus = deriveStatus({
    snapshot,
    winePrefixPresent,
    fileBridgePresent,
    hasPassword: env.hasMt5Password,
    usedOperator,
  });

  const bookHonesty = liveBalance
    ? `Live FundedNext MT5 ${FUNDEDNEXT_EXPECTED_LOGIN} @ ${
        snapshot?.server || FUNDEDNEXT_EXPECTED_SERVER
      }. Read-only file-bridge snapshot. Live OrderSend is the FundedNext live copy control.`
    : winePrefixPresent
      ? "FundedNext Wine prefix is on disk. Waiting for a fresh Mt5ArchBridge account.json (read-only EA). Live OrderSend is the FundedNext live copy control."
      : "FundedNext Wine prefix is missing. Card stays on the operator login/server; paper copy is unchanged.";

  return {
    source: "operator-env",
    fetchedAt: new Date().toISOString(),
    usedOperatorEnv: usedOperator,
    ordersPlaced: false,
    winePrefixPresent,
    fileBridgePresent,
    connectionStatus,
    login: snapshot?.login || env.mt5Login,
    server: snapshot?.server || env.mt5Server,
    platform: "MT5",
    balance: snapshot?.balance ?? null,
    equity: snapshot?.equity ?? null,
    currency: snapshot?.currency ?? null,
    leverage: snapshot?.leverage ?? null,
    name: snapshot?.name ?? null,
    terminalConnected: snapshot?.terminalConnected ?? null,
    hasPassword: env.hasMt5Password,
    bookHonesty,
    fetchNotes: notes,
    nextSecretNeeded: liveBalance
      ? null
      : env.hasMt5Password
        ? "A running ~/.mt5-fundednext terminal with read-only Mt5ArchBridge writing account.json."
        : `FUNDEDNEXT_MT5_PASSWORD for login ${FUNDEDNEXT_EXPECTED_LOGIN}.`,
  };
}

export function fundednextAccountSnapshot(report: FundedNextLiveReport) {
  return {
    connectionStatus: report.connectionStatus,
    login: report.login,
    server: report.server,
    platform: report.platform,
    balance: report.balance,
    equity: report.equity,
    currency: report.currency,
    terminalConnected: report.terminalConnected,
    fetchedAt: report.fetchedAt,
    usedOperatorEnv: report.usedOperatorEnv,
    bookHonesty: report.bookHonesty,
    fetchNotes: report.fetchNotes,
    ordersPlaced: report.ordersPlaced,
    nextSecretNeeded: report.nextSecretNeeded,
    winePrefixPresent: report.winePrefixPresent,
    fileBridgePresent: report.fileBridgePresent,
  };
}
