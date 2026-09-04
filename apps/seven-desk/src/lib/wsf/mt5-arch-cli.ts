import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { WSF_EXPECTED_LOGIN } from "@/lib/wsf/constants";
import type { WsfDealRow, WsfFetchedAccount, WsfPositionRow } from "@/lib/wsf/types";

export interface Mt5ArchCliResult {
  book: WsfFetchedAccount | null;
  positions: WsfPositionRow[];
  deals: WsfDealRow[];
  note: string;
}

function archRoot(): string {
  return (
    process.env.MT5_ARCH_ROOT ||
    join(homedir(), "Projects/trading/mt5-arch-integration")
  );
}

function uvCommand(): string {
  const local = join(homedir(), ".local/bin/uv");
  return existsSync(local) ? local : "uv";
}

export function probeMt5ArchCli(): Mt5ArchCliResult {
  const root = archRoot();
  if (!existsSync(join(root, "pyproject.toml"))) {
    return {
      book: null,
      positions: [],
      deals: [],
      note: "mt5-arch-integration tree not found on this host.",
    };
  }
  try {
    const winePrefix = join(homedir(), ".mt5-wsf");
    const brands = ["WSFmarkets MT5 Terminal"];
    let bridgeDir = process.env.WSF_MT5_BRIDGE_DIR || "";
    if (bridgeDir && !bridgeDir.includes(".mt5-wsf")) {
      bridgeDir = "";
    }
    if (!bridgeDir) {
      for (const brand of brands) {
        const dir = join(winePrefix, "drive_c", "Program Files", brand, "MQL5", "Files", "mt5_arch");
        if (existsSync(join(dir, "account.json"))) {
          bridgeDir = dir;
          break;
        }
      }
    }
    const result = spawnSync(uvCommand(), ["run", "mt5-arch", "account", "--json"], {
      cwd: root,
      encoding: "utf8",
      timeout: 12000,
      env: {
        ...process.env,
        WINEPREFIX: winePrefix,
        MT5_BACKEND: process.env.MT5_BACKEND || "file",
        ...(bridgeDir ? { MT5_BRIDGE_DIR: bridgeDir } : {}),
      },
    });
    const out = (result.stdout || "").trim();
    const err = (result.stderr || "").trim();
    if (result.error) {
      const missing = result.error.message.includes("ENOENT")
        ? "uv not installed on this host"
        : result.error.message;
      return {
        book: null,
        positions: [],
        deals: [],
        note: `mt5-arch CLI error: ${missing}`,
      };
    }
    if (result.status !== 0) {
      const hint = err.split("\n").find((line) => line.trim()) || `exit ${result.status}`;
      return {
        book: null,
        positions: [],
        deals: [],
        note: `uv run mt5-arch account failed closed (expected without Wine): ${hint.slice(0, 180)}`,
      };
    }
    const parsed = JSON.parse(out) as {
      login?: number | string;
      balance?: number;
      equity?: number;
      currency?: string;
      leverage?: number;
      server?: string;
      name?: string;
    };
    const login = parsed.login != null ? String(parsed.login) : "";
    if (login && login !== WSF_EXPECTED_LOGIN) {
      return {
        book: null,
        positions: [],
        deals: [],
        note: `Refusing snapshot login ${login} — expected ${WSF_EXPECTED_LOGIN}.`,
      };
    }
    return {
      book: login
        ? {
            source: "mt5-env",
            kind: "personal-env",
            broker: parsed.server || "WSFmarkets-Server",
            accountId: login,
            login,
            name: parsed.name || `WSF MT5 ${login}`,
            environment: "unknown",
            accountType: null,
            balance: typeof parsed.balance === "number" ? parsed.balance : null,
            equity: typeof parsed.equity === "number" ? parsed.equity : null,
            currency: parsed.currency || null,
            leverage: parsed.leverage ? `1:${parsed.leverage}` : null,
            plantIsWsf: true,
          }
        : null,
      positions: [],
      deals: [] as WsfDealRow[],
      note: `mt5-arch account --json succeeded for login ${login || "unknown"}.`,
    };
  } catch (error) {
    return {
      book: null,
      positions: [],
      deals: [],
      note:
        error instanceof Error
          ? `mt5-arch CLI not runnable: ${error.message}`
          : "mt5-arch CLI not runnable.",
    };
  }
}
