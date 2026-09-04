import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, unlinkSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, relative, resolve } from "node:path";
import {
  ALPHACAPITAL_BRAND_INSTALLS,
  ALPHACAPITAL_EXPECTED_LOGIN,
  ALPHACAPITAL_ONLY_PREFIX,
  ALPHACAPITAL_SERVER_NEEDLE,
} from "@/lib/alphacapital/env";
import { ALPHACAPITAL_EXPECTED_SERVER, ALPHACAPITAL_LIVE_CONFIRM } from "@/lib/alphacapital/types";
import {
  FUNDEDNEXT_BRAND_INSTALLS,
  FUNDEDNEXT_EXPECTED_LOGIN,
  FUNDEDNEXT_ONLY_PREFIX,
  FUNDEDNEXT_SERVER_NEEDLE,
} from "@/lib/fundednext/env";
import { FUNDEDNEXT_EXPECTED_SERVER, FUNDEDNEXT_LIVE_CONFIRM } from "@/lib/fundednext/types";
import {
  FTMO_BRAND_INSTALLS,
  FTMO_EXPECTED_LOGIN,
  FTMO_ONLY_PREFIX,
  FTMO_SERVER_NEEDLE,
} from "@/lib/ftmo/env";
import { FTMO_EXPECTED_SERVER, FTMO_LIVE_CONFIRM } from "@/lib/ftmo/types";
import type { LiveBroker, LiveOrderAction, LiveOrderInput, LiveOrderResult } from "@/lib/live-order/types";

const SCRIPT_NAME = "DeskLiveOrder";
const FORBIDDEN = [".mt5-vantage", ".mt5-fpmarkets", ".mt5-exness"] as const;
const ALLOWED_SYMBOLS = new Set(["EURUSD", "EURUSDc"]);
const MIN_LOT = 0.01;

export type DeskLiveFirm = Exclude<LiveBroker, "wsf">;

interface FirmSpec {
  id: DeskLiveFirm;
  prefix: string;
  brands: readonly string[];
  login: string;
  confirm: string;
  needle: string;
  server: string;
  magic: number;
  defaultSymbol: string;
  restoreArg: DeskLiveFirm;
}

const FIRMS: Record<DeskLiveFirm, FirmSpec> = {
  ftmo: {
    id: "ftmo",
    prefix: FTMO_ONLY_PREFIX,
    brands: FTMO_BRAND_INSTALLS,
    login: FTMO_EXPECTED_LOGIN,
    confirm: FTMO_LIVE_CONFIRM,
    needle: FTMO_SERVER_NEEDLE,
    server: FTMO_EXPECTED_SERVER,
    magic: 20263848,
    defaultSymbol: "EURUSD",
    restoreArg: "ftmo",
  },
  fundednext: {
    id: "fundednext",
    prefix: FUNDEDNEXT_ONLY_PREFIX,
    brands: FUNDEDNEXT_BRAND_INSTALLS,
    login: FUNDEDNEXT_EXPECTED_LOGIN,
    confirm: FUNDEDNEXT_LIVE_CONFIRM,
    needle: FUNDEDNEXT_SERVER_NEEDLE,
    server: FUNDEDNEXT_EXPECTED_SERVER,
    magic: 20263849,
    defaultSymbol: "EURUSD",
    restoreArg: "fundednext",
  },
  alphacapital: {
    id: "alphacapital",
    prefix: ALPHACAPITAL_ONLY_PREFIX,
    brands: ALPHACAPITAL_BRAND_INSTALLS,
    login: ALPHACAPITAL_EXPECTED_LOGIN,
    confirm: ALPHACAPITAL_LIVE_CONFIRM,
    needle: ALPHACAPITAL_SERVER_NEEDLE,
    server: ALPHACAPITAL_EXPECTED_SERVER,
    magic: 20263850,
    defaultSymbol: "EURUSD",
    restoreArg: "alphacapital",
  },
};

interface GuardOk {
  ok: true;
  action: LiveOrderAction;
  symbol: string;
  side: "BUY" | "SELL";
  useVolumeMin: boolean;
  volume: number | null;
  confirm: string;
}

interface GuardFail {
  ok: false;
  status: number;
  result: LiveOrderResult;
}

function deskRoot(): string {
  return resolve(join(process.cwd(), process.cwd().endsWith("seven-desk") ? "." : "apps/seven-desk"));
}

function repoRoot(): string {
  const cwd = process.cwd();
  if (cwd.endsWith("seven-desk")) return resolve(join(cwd, "../.."));
  return resolve(cwd);
}

function real(path: string): string {
  try {
    return resolve(path);
  } catch {
    return path;
  }
}

function winePrefixLabel(prefix: string): string {
  return `.${relative(homedir(), prefix)}`.replace(/^\.\./, ".") || prefix;
}

function fail(
  firm: FirmSpec,
  status: number,
  stage: string,
  reason: string,
  extra?: Partial<LiveOrderResult>
): GuardFail {
  return {
    ok: false,
    status,
    result: {
      ok: false,
      source: "seven-desk",
      endpoint: extra?.endpoint ?? `/api/${firm.id}/order`,
      requestId: extra?.requestId ?? "",
      stage,
      reason,
      login: extra?.login ?? null,
      server: extra?.server ?? null,
      winePrefix: winePrefixLabel(firm.prefix),
      ...extra,
    },
  };
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function validateBody(firm: FirmSpec, body: LiveOrderInput): GuardOk | GuardFail {
  if (body.live !== true) {
    return fail(firm, 400, "confirm", "live must be true — paper is the default");
  }
  const confirm = asString(body.confirm);
  if (confirm !== firm.confirm) {
    return fail(firm, 403, "confirm", `confirm must be exactly ${firm.confirm}`);
  }
  const actionRaw = asString(body.action).toLowerCase() || "scratch";
  if (actionRaw !== "scratch" && actionRaw !== "open" && actionRaw !== "close") {
    return fail(firm, 400, "action", "action must be scratch, open, or close");
  }
  const symbol = asString(body.symbol) || firm.defaultSymbol;
  if (!ALLOWED_SYMBOLS.has(symbol)) {
    return fail(firm, 400, "symbol", "symbol not allowed — EURUSD/EURUSDc only");
  }
  const sideRaw = asString(body.side).toLowerCase() || "buy";
  if (sideRaw !== "buy" && sideRaw !== "sell") {
    return fail(firm, 400, "side", "side must be buy or sell");
  }
  const volumeMinFlag = body.volume_min === true || body.volume === undefined || body.volume === null;
  let volume: number | null = null;
  if (body.volume !== undefined && body.volume !== null && body.volume !== "") {
    volume = typeof body.volume === "number" ? body.volume : Number(body.volume);
    if (!Number.isFinite(volume)) {
      return fail(firm, 400, "volume", "volume must be a number");
    }
    if (!volumeMinFlag && Math.abs(volume - MIN_LOT) > 1e-8) {
      return fail(firm, 400, "volume", "volume must be the symbol minimum (0.01) or pass volume_min=true");
    }
    if (volume > MIN_LOT + 1e-8) {
      return fail(firm, 400, "volume", "volume exceeds symbol minimum — refusing larger size");
    }
  }
  return {
    ok: true,
    action: actionRaw,
    symbol,
    side: sideRaw === "sell" ? "SELL" : "BUY",
    useVolumeMin: volumeMinFlag || volume == null,
    volume,
    confirm,
  };
}

function assertAllowedPrefix(prefix: string, expected: string): string | null {
  const resolved = real(prefix);
  if (resolved !== real(expected)) {
    return `WINEPREFIX is not ${winePrefixLabel(expected)} — refusing live order`;
  }
  for (const marker of FORBIDDEN) {
    if (resolved.includes(marker)) {
      return `forbidden prefix ${marker} — refusing live order`;
    }
  }
  return null;
}

function brandDir(firm: FirmSpec): string {
  return join(firm.prefix, "drive_c", "Program Files", firm.brands[0]);
}

function terminalCwd(pid: number): string {
  try {
    return spawnSync("readlink", ["-f", `/proc/${pid}/cwd`], { encoding: "utf8" }).stdout.trim();
  } catch {
    return "";
  }
}

function isGenericTree(cwd: string): boolean {
  return /\/Program Files\/MetaTrader 5\/?$/.test(cwd);
}

function pathsFor(firm: FirmSpec) {
  const prefixError = assertAllowedPrefix(firm.prefix, firm.prefix);
  const brand = brandDir(firm);
  const bridgeDir = join(brand, "MQL5", "Files", "mt5_arch");
  return {
    prefix: firm.prefix,
    prefixError,
    brandDir: brand,
    terminalExe: join(brand, "terminal64.exe"),
    metaEditor: join(brand, "MetaEditor64.exe"),
    scriptsDir: join(brand, "MQL5", "Scripts"),
    scriptSrcRepo: join(deskRoot(), "mql5", `${SCRIPT_NAME}.mq5`),
    scriptSrcPrefix: join(brand, "MQL5", "Scripts", `${SCRIPT_NAME}.mq5`),
    scriptEx5: join(brand, "MQL5", "Scripts", `${SCRIPT_NAME}.ex5`),
    autoLogin: join(brand, "auto_login.ini"),
    accountJson: join(bridgeDir, "account.json"),
    requestFile: join(bridgeDir, "desk_live_order_request.txt"),
    resultFile: join(bridgeDir, "desk_live_order_result.json"),
    configIni: join(brand, "desk_live_order.ini"),
    bridgeDir,
    extraBridgeDirs: commonBridgeDirs(firm.prefix),
  };
}

function commonBridgeDirs(prefix: string): string[] {
  const users = join(prefix, "drive_c", "users");
  const out: string[] = [];
  if (!existsSync(users)) return out;
  try {
    for (const name of readdirSync(users)) {
      out.push(
        join(users, name, "AppData", "Roaming", "MetaQuotes", "Terminal", "Common", "Files", "mt5_arch")
      );
    }
  } catch {
    return out;
  }
  return out;
}

function quotesReady(brandDir: string, symbol: string): boolean {
  const bases = join(brandDir, "Bases");
  if (!existsSync(bases)) return false;
  const want = symbol.toUpperCase();
  const stack = [bases];
  while (stack.length > 0) {
    const dir = stack.pop();
    if (!dir) break;
    let names: string[] = [];
    try {
      names = readdirSync(dir);
    } catch {
      continue;
    }
    for (const name of names) {
      const full = join(dir, name);
      let st;
      try {
        st = statSync(full);
      } catch {
        continue;
      }
      if (st.isDirectory()) {
        stack.push(full);
        continue;
      }
      if (st.size <= 0) continue;
      const upper = full.toUpperCase();
      const file = name.toUpperCase();
      if (!upper.includes(`/${want}/`) && !upper.includes(`\\${want}\\`) && !file.startsWith(want)) {
        continue;
      }
      if (file.endsWith(".HCC") || file.endsWith(".HC") || file.endsWith(".TKC")) return true;
      if (upper.includes("/HISTORY/") || upper.includes("/TICKS/") || upper.includes("\\HISTORY\\") || upper.includes("\\TICKS\\")) {
        return true;
      }
    }
  }
  return false;
}

function wineEnv(prefix: string): NodeJS.ProcessEnv {
  const env = { ...process.env };
  env.WINEPREFIX = prefix;
  env.WINEARCH = "win64";
  env.WINEDEBUG = "-all";
  env.DISPLAY = process.env.DISPLAY || ":0";
  delete env.WAYLAND_DISPLAY;
  delete env.LD_PRELOAD;
  env.WINEDLLOVERRIDES = process.env.WINEDLLOVERRIDES || "d3d11=b;d3d12=b;dxgi=b";
  return env;
}

function listPrefixPids(prefix: string): number[] {
  const want = real(prefix);
  const pids: number[] = [];
  let names: string[] = [];
  try {
    names = readdirSync("/proc").filter((name) => /^\d+$/.test(name));
  } catch {
    return pids;
  }
  for (const pid of names) {
    try {
      const cmd = readFileSync(`/proc/${pid}/cmdline`).toString("utf8").replace(/\0/g, " ");
      if (!cmd.includes("terminal64.exe") || cmd.includes("bash")) continue;
      let got = "";
      try {
        const env = readFileSync(`/proc/${pid}/environ`).toString("utf8");
        for (const part of env.split("\0")) {
          if (part.startsWith("WINEPREFIX=")) {
            got = real(part.slice("WINEPREFIX=".length));
            break;
          }
        }
      } catch {
        got = "";
      }
      if (got === want) pids.push(Number(pid));
    } catch {
      continue;
    }
  }
  return pids;
}

function stopPrefix(prefix: string): number[] {
  const stopped = listPrefixPids(prefix);
  for (const pid of stopped) {
    try {
      process.kill(pid, "SIGTERM");
    } catch {
      // gone
    }
  }
  const deadline = Date.now() + 4000;
  while (Date.now() < deadline && listPrefixPids(prefix).length > 0) {
    spawnSync("sleep", ["0.2"]);
  }
  for (const pid of listPrefixPids(prefix)) {
    try {
      process.kill(pid, "SIGKILL");
    } catch {
      // gone
    }
  }
  return stopped;
}

function stopGenericPrefixPids(prefix: string): number[] {
  const stopped: number[] = [];
  for (const pid of listPrefixPids(prefix)) {
    if (!isGenericTree(terminalCwd(pid))) continue;
    try {
      process.kill(pid, "SIGTERM");
      stopped.push(pid);
    } catch {
      // gone
    }
  }
  return stopped;
}

function restoreTerminal(firm: FirmSpec): string {
  const leftover = stopGenericPrefixPids(firm.prefix);
  const helper = join(repoRoot(), "scripts/21-start-broker-background.sh");
  const child = spawn(helper, [firm.restoreArg], { detached: true, stdio: "ignore" });
  child.unref();
  const extra = leftover.length ? `; stopped generic leftover ${leftover.join(",")}` : "";
  return `restored ${firm.id} via background helper pid ${child.pid ?? "?"}${extra}`;
}

function compileScript(firm: FirmSpec, paths: ReturnType<typeof pathsFor>): string | null {
  if (!existsSync(paths.scriptSrcRepo)) {
    return `desk MQL source missing at ${relative(repoRoot(), paths.scriptSrcRepo)}`;
  }
  mkdirSync(paths.scriptsDir, { recursive: true });
  mkdirSync(paths.bridgeDir, { recursive: true });
  writeFileSync(paths.scriptSrcPrefix, readFileSync(paths.scriptSrcRepo));
  const needCompile =
    !existsSync(paths.scriptEx5) ||
    statSync(paths.scriptSrcPrefix).mtimeMs > statSync(paths.scriptEx5).mtimeMs;
  if (!needCompile) return null;
  const result = spawnSync("wine", [paths.metaEditor, `/compile:${SCRIPT_NAME}.mq5`, "/log"], {
    cwd: paths.scriptsDir,
    encoding: "utf8",
    timeout: 45000,
    env: wineEnv(firm.prefix),
  });
  if (!existsSync(paths.scriptEx5)) {
    let hint = result.stderr?.slice(0, 180) || `compile exit ${result.status}`;
    const logPath = join(paths.scriptsDir, `${SCRIPT_NAME}.log`);
    if (existsSync(logPath)) {
      const raw = readFileSync(logPath);
      const text = raw[1] === 0 ? raw.toString("utf16le") : raw.toString("utf8");
      const last = text
        .split(/\r?\n/)
        .filter((line) => line.trim())
        .slice(-4)
        .join(" | ");
      if (last) hint = last.slice(0, 240);
    }
    return `MetaEditor compile failed: ${hint}`;
  }
  return null;
}

function readAutoLoginPassword(autoLogin: string): string {
  if (!existsSync(autoLogin)) return "";
  const text = readFileSync(autoLogin, "utf8");
  for (const line of text.replace(/\r/g, "").split("\n")) {
    if (line.startsWith("Password=")) return line.slice("Password=".length);
  }
  return "";
}

function writeRequest(firm: FirmSpec, paths: ReturnType<typeof pathsFor>, parsed: GuardOk, requestId: string): void {
  const body = [
    `request_id=${requestId}`,
    `action=${parsed.action}`,
    `symbol=${parsed.symbol}`,
    `side=${parsed.side}`,
    `confirm=${parsed.confirm}`,
    `expect_confirm=${firm.confirm}`,
    `expect_login=${firm.login}`,
    `expect_needle=${firm.needle}`,
    `volume=${parsed.volume ?? MIN_LOT}`,
    `use_volume_min=${parsed.useVolumeMin ? 1 : 0}`,
    `magic=${firm.magic}`,
    "",
  ].join("\n");
  mkdirSync(paths.bridgeDir, { recursive: true });
  writeFileSync(paths.requestFile, body, { encoding: "utf8" });
  for (const dir of paths.extraBridgeDirs) {
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "desk_live_order_request.txt"), body, { encoding: "utf8" });
  }
}

function writeStartupIni(firm: FirmSpec, paths: ReturnType<typeof pathsFor>, symbol: string): string | null {
  const password = readAutoLoginPassword(paths.autoLogin);
  const common = [
    "[Common]",
    `Login=${firm.login}`,
    `Server=${firm.server}`,
    "ProxyEnable=0",
    "KeepPrivate=1",
    "NewsEnable=0",
    "CertInstall=1",
  ];
  if (password) common.splice(3, 0, `Password=${password}`);
  const text = `${common.join("\n")}
[Charts]
MaxBars=100000
PreloadCharts=1
[Experts]
AllowLiveTrading=1
Enabled=1
Account=1
Profile=1
Chart=1
[StartUp]
Script=${SCRIPT_NAME}
Symbol=${symbol}
Period=M1
ShutdownTerminal=1
`;
  writeFileSync(paths.configIni, text.replace(/\n/g, "\r\n"), { encoding: "ascii", mode: 0o600 });
  return null;
}

function readBridgeIdentity(accountJson: string): { login: string | null; server: string | null; company: string | null } {
  if (!existsSync(accountJson)) return { login: null, server: null, company: null };
  try {
    const raw = JSON.parse(readFileSync(accountJson, "utf8")) as Record<string, unknown>;
    return {
      login: raw.login != null ? String(raw.login) : null,
      server: raw.server != null ? String(raw.server) : null,
      company: raw.company != null ? String(raw.company) : null,
    };
  } catch {
    return { login: null, server: null, company: null };
  }
}

function parseResultJson(text: string): Partial<LiveOrderResult> {
  try {
    const raw = JSON.parse(text) as Record<string, unknown>;
    return {
      ok: raw.ok === true,
      requestId: raw.request_id != null ? String(raw.request_id) : "",
      stage: raw.stage != null ? String(raw.stage) : "",
      reason: raw.reason != null ? String(raw.reason) : "",
      login: raw.login != null ? Number(raw.login) : null,
      server: raw.server != null ? String(raw.server) : null,
      company: raw.company != null ? String(raw.company) : undefined,
      symbol: raw.symbol != null ? String(raw.symbol) : undefined,
      volume: typeof raw.volume === "number" ? raw.volume : undefined,
      side: raw.side != null ? String(raw.side) : undefined,
      order: typeof raw.order === "number" ? raw.order : undefined,
      position: typeof raw.position === "number" ? raw.position : undefined,
      dealOpen: typeof raw.deal_open === "number" ? raw.deal_open : undefined,
      dealClose: typeof raw.deal_close === "number" ? raw.deal_close : undefined,
      openPrice: typeof raw.open_price === "number" ? raw.open_price : undefined,
      closePrice: typeof raw.close_price === "number" ? raw.close_price : undefined,
      profit: typeof raw.profit === "number" ? raw.profit : undefined,
      holdMs: typeof raw.hold_ms === "number" ? raw.hold_ms : undefined,
      balanceAfter: typeof raw.balance_after === "number" ? raw.balance_after : undefined,
      closeRetcode: typeof raw.close_retcode === "number" ? raw.close_retcode : undefined,
    };
  } catch {
    return { ok: false, stage: "result", reason: "result JSON parse failed" };
  }
}

function resultCandidates(paths: ReturnType<typeof pathsFor>): string[] {
  return [
    paths.resultFile,
    ...paths.extraBridgeDirs.map((dir) => join(dir, "desk_live_order_result.json")),
  ];
}

function waitResult(paths: ReturnType<typeof pathsFor>, timeoutMs: number): Partial<LiveOrderResult> {
  const deadline = Date.now() + timeoutMs;
  const files = resultCandidates(paths);
  while (Date.now() < deadline) {
    for (const resultFile of files) {
      if (existsSync(resultFile)) {
        return parseResultJson(readFileSync(resultFile, "utf8"));
      }
    }
    spawnSync("sleep", ["0.4"]);
  }
  return { ok: false, stage: "timeout", reason: "one-shot produced no result json" };
}

function waitQuotesOrFresh(
  firm: FirmSpec,
  paths: ReturnType<typeof pathsFor>,
  symbol: string,
  timeoutMs: number
): boolean {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (quotesReady(paths.brandDir, symbol)) return true;
    if (existsSync(join(paths.bridgeDir, "heartbeat.txt"))) {
      try {
        if (Date.now() - statSync(join(paths.bridgeDir, "heartbeat.txt")).mtimeMs < 60000) {
          return true;
        }
      } catch {
        // ignore
      }
    }
    spawnSync("sleep", ["1"]);
  }
  return quotesReady(paths.brandDir, symbol);
}

function newRequestId(firm: DeskLiveFirm): string {
  return `${firm}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

export async function executeDeskLiveOrder(
  firmId: DeskLiveFirm,
  body: LiveOrderInput,
  endpoint: string
): Promise<{ status: number; result: LiveOrderResult }> {
  const firm = FIRMS[firmId];
  const requestId = newRequestId(firmId);
  const parsed = validateBody(firm, body);
  if (!parsed.ok) {
    parsed.result.requestId = requestId;
    parsed.result.endpoint = endpoint;
    return { status: parsed.status, result: parsed.result };
  }

  const paths = pathsFor(firm);
  if (paths.prefixError) {
    return { status: 409, result: fail(firm, 409, "prefix", paths.prefixError, { requestId, endpoint }).result };
  }
  if (!existsSync(paths.prefix) || !existsSync(paths.terminalExe)) {
    return {
      status: 409,
      result: fail(firm, 409, "prefix", `${firm.id} brand terminal is not installed`, { requestId, endpoint }).result,
    };
  }
  if (!existsSync(paths.metaEditor)) {
    return {
      status: 409,
      result: fail(firm, 409, "compile", `${firm.id} MetaEditor64.exe missing`, { requestId, endpoint }).result,
    };
  }

  const identity = readBridgeIdentity(paths.accountJson);
  if (identity.login && identity.login !== firm.login) {
    return {
      status: 409,
      result: fail(firm, 409, "account", `file-bridge login is not ${firm.login} — refusing OrderSend`, {
        requestId,
        endpoint,
        login: Number(identity.login),
        server: identity.server,
      }).result,
    };
  }
  if (identity.server && !identity.server.includes(firm.needle)) {
    return {
      status: 409,
      result: fail(firm, 409, "account", `file-bridge server is not ${firm.needle} — refusing OrderSend`, {
        requestId,
        endpoint,
        login: identity.login ? Number(identity.login) : null,
        server: identity.server,
      }).result,
    };
  }

  const compileError = compileScript(firm, paths);
  if (compileError) {
    return {
      status: 500,
      result: fail(firm, 500, "compile", compileError, {
        requestId,
        endpoint,
        login: identity.login ? Number(identity.login) : null,
        server: identity.server,
      }).result,
    };
  }

  writeStartupIni(firm, paths, parsed.symbol);
  for (const resultFile of resultCandidates(paths)) {
    if (existsSync(resultFile)) {
      try {
        unlinkSync(resultFile);
      } catch {
        // ignore
      }
    }
  }
  writeRequest(firm, paths, parsed, requestId);

  if (firm.id === "alphacapital" && !quotesReady(paths.brandDir, parsed.symbol)) {
    const ready = waitQuotesOrFresh(firm, paths, parsed.symbol, 90000);
    if (!ready) {
      return {
        status: 409,
        result: fail(firm, 409, "symbol", "EURUSD not synchronized — no history/ticks yet; not sending OrderSend", {
          requestId,
          endpoint,
          login: identity.login ? Number(identity.login) : null,
          server: identity.server,
        }).result,
      };
    }
  }

  const stopped = stopPrefix(firm.prefix);
  let wineStatus: number | null = null;
  const wineTimeout = firm.id === "alphacapital" ? 180000 : 90000;
  try {
    const run = spawnSync("wine", ["./terminal64.exe", "/portable", "/config:desk_live_order.ini"], {
      cwd: paths.brandDir,
      encoding: "utf8",
      timeout: wineTimeout,
      env: wineEnv(firm.prefix),
    });
    wineStatus = run.status;
  } catch (caught) {
    wineStatus = null;
    if (!(caught instanceof Error && /ETIMEDOUT|timeout/i.test(caught.message))) {
      const restoreNote = restoreTerminal(firm);
      try {
        unlinkSync(paths.configIni);
      } catch {
        // drop leftover ini
      }
      return {
        status: 500,
        result: fail(firm, 500, "wine", caught instanceof Error ? caught.message : "wine failed", {
          requestId,
          endpoint,
          restoreNote,
        }).result,
      };
    }
  }

  const haveResult = resultCandidates(paths).some((path) => existsSync(path));
  const parsedResult = waitResult(paths, haveResult ? 1000 : 20000);
  if (!parsedResult.ok && parsedResult.stage === "timeout" && wineStatus != null) {
    parsedResult.reason = `${parsedResult.reason} (wine status ${wineStatus})`;
  }

  const result: LiveOrderResult = {
    ok: parsedResult.ok === true,
    source: "seven-desk",
    endpoint,
    requestId,
    stage: parsedResult.stage || "unknown",
    reason: parsedResult.reason || "",
    login: parsedResult.login ?? (identity.login ? Number(identity.login) : null),
    server: parsedResult.server ?? identity.server,
    company: parsedResult.company ?? identity.company ?? undefined,
    symbol: parsedResult.symbol ?? parsed.symbol,
    volume: parsedResult.volume,
    side: parsedResult.side ?? parsed.side,
    order: parsedResult.order,
    position: parsedResult.position,
    dealOpen: parsedResult.dealOpen,
    dealClose: parsedResult.dealClose,
    openPrice: parsedResult.openPrice,
    closePrice: parsedResult.closePrice,
    profit: parsedResult.profit,
    holdMs: parsedResult.holdMs,
    balanceAfter: parsedResult.balanceAfter,
    closeRetcode: parsedResult.closeRetcode,
    winePrefix: winePrefixLabel(firm.prefix),
    stoppedPids: stopped,
    restoreNote: "",
  };

  try {
    unlinkSync(paths.configIni);
  } catch {
    // leftover ini may contain a password — best-effort drop
  }
  result.restoreNote = restoreTerminal(firm);
  if (result.login != null && Number(result.login) !== Number(firm.login)) {
    result.ok = false;
    result.stage = "account";
    result.reason = `result login is not ${firm.login}`;
  }
  const status = result.ok ? 200 : result.stage === "timeout" ? 504 : 409;
  return { status, result };
}

export function handleLiveOrderPost(firmId: DeskLiveFirm, endpoint: string, forceAction?: LiveOrderAction) {
  return async (request: Request): Promise<Response> => {
    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return Response.json(
        {
          ok: false,
          source: "seven-desk",
          endpoint,
          stage: "body",
          reason: "JSON body required",
          winePrefix: winePrefixLabel(FIRMS[firmId].prefix),
        },
        { status: 400 }
      );
    }
    const payload = body && typeof body === "object" ? (body as Record<string, unknown>) : {};
    const { status, result } = await executeDeskLiveOrder(
      firmId,
      {
        live: payload.live,
        confirm: payload.confirm,
        action: forceAction ?? payload.action,
        symbol: payload.symbol,
        side: payload.side,
        volume: payload.volume,
        volume_min: payload.volume_min,
      },
      endpoint
    );
    return Response.json(result, { status });
  };
}
