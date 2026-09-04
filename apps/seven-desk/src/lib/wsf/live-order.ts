import { spawn, spawnSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, statSync, unlinkSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, relative, resolve } from "node:path";
import {
  WSF_EXPECTED_LOGIN,
  WSF_LIVE_CONFIRM,
  WSF_SERVER_NEEDLE,
  resolveWsfOnlyPrefix,
  wsfBrandTerminalDir,
} from "@/lib/wsf/env";
import type { WsfLiveOrderAction, WsfLiveOrderResult } from "@/lib/wsf/types";

export const WSF_LIVE_MAGIC = 20263847;
const ALLOWED_SYMBOLS = new Set(["EURUSDc", "EURUSD"]);
const FORBIDDEN_PREFIX_MARKERS = [".mt5-vantage", ".mt5-fpmarkets", ".mt5-exness"];
const CONSERVATIVE_FX_MIN = 0.01;
const HEARTBEAT_MAX_AGE_SEC = 90;
const SCRIPT_NAME = "WsfDeskLiveOrder";

export interface WsfLiveOrderInput {
  live: unknown;
  confirm: unknown;
  action?: unknown;
  symbol?: unknown;
  side?: unknown;
  volume?: unknown;
  volume_min?: unknown;
}

export interface GuardOk {
  ok: true;
  action: WsfLiveOrderAction;
  symbol: string;
  side: "BUY" | "SELL";
  useVolumeMin: boolean;
  volume: number | null;
  confirm: string;
}

export interface GuardFail {
  ok: false;
  status: number;
  result: WsfLiveOrderResult;
}

function deskRoot(): string {
  return resolve(join(process.cwd(), process.cwd().endsWith("seven-desk") ? "." : "apps/seven-desk"));
}

function repoRoot(): string {
  const cwd = process.cwd();
  if (cwd.endsWith("seven-desk")) return resolve(join(cwd, "../.."));
  return resolve(cwd);
}

function fail(
  status: number,
  stage: string,
  reason: string,
  extra?: Partial<WsfLiveOrderResult>
): GuardFail {
  return {
    ok: false,
    status,
    result: {
      ok: false,
      source: "seven-desk",
      endpoint: extra?.endpoint ?? "/api/wsf/order",
      requestId: extra?.requestId ?? "",
      stage,
      reason,
      login: extra?.login ?? null,
      server: extra?.server ?? null,
      winePrefix: ".mt5-wsf",
      ...extra,
    },
  };
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function validateLiveOrderBody(body: WsfLiveOrderInput): GuardOk | GuardFail {
  if (body.live !== true) {
    return fail(400, "confirm", "live must be true — paper is the default");
  }
  const confirm = asString(body.confirm);
  if (confirm !== WSF_LIVE_CONFIRM) {
    return fail(403, "confirm", `confirm must be exactly ${WSF_LIVE_CONFIRM}`);
  }
  const actionRaw = asString(body.action).toLowerCase() || "scratch";
  if (actionRaw !== "scratch" && actionRaw !== "open" && actionRaw !== "close") {
    return fail(400, "action", "action must be scratch, open, or close");
  }
  const symbol = asString(body.symbol) || "EURUSDc";
  if (!ALLOWED_SYMBOLS.has(symbol)) {
    return fail(400, "symbol", "symbol not allowed — EURUSDc/EURUSD only on the WSF live path");
  }
  const sideRaw = asString(body.side).toLowerCase() || "buy";
  if (sideRaw !== "buy" && sideRaw !== "sell") {
    return fail(400, "side", "side must be buy or sell");
  }
  const volumeMinFlag = body.volume_min === true || body.volume === undefined || body.volume === null;
  let volume: number | null = null;
  if (body.volume !== undefined && body.volume !== null && body.volume !== "") {
    volume = typeof body.volume === "number" ? body.volume : Number(body.volume);
    if (!Number.isFinite(volume)) {
      return fail(400, "volume", "volume must be a number");
    }
    if (!volumeMinFlag && Math.abs(volume - CONSERVATIVE_FX_MIN) > 1e-8) {
      return fail(
        400,
        "volume",
        "volume must be the symbol minimum (0.01) or pass volume_min=true"
      );
    }
    if (volume > CONSERVATIVE_FX_MIN + 1e-8) {
      return fail(400, "volume", "volume exceeds symbol minimum — refusing larger size");
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

function real(path: string): string {
  try {
    return resolve(path);
  } catch {
    return path;
  }
}

export function assertWsfOnlyPrefix(prefix: string): string | null {
  const resolved = real(prefix);
  const expected = real(resolveWsfOnlyPrefix());
  if (resolved !== expected) {
    return "WINEPREFIX is not ~/.mt5-wsf — refusing live order";
  }
  for (const marker of FORBIDDEN_PREFIX_MARKERS) {
    if (resolved.includes(marker)) {
      return `forbidden prefix ${marker} — refusing live order`;
    }
  }
  if (resolved.includes(".mt5-vantage") || resolved.includes(".mt5-fpmarkets")) {
    return "refusing Vantage/FP prefix";
  }
  return null;
}

function wsfPaths() {
  const prefix = resolveWsfOnlyPrefix();
  const prefixError = assertWsfOnlyPrefix(prefix);
  const brandDir = wsfBrandTerminalDir();
  const bridgeDir = join(brandDir, "MQL5", "Files", "mt5_arch");
  return {
    prefix,
    prefixError,
    brandDir,
    terminalExe: join(brandDir, "terminal64.exe"),
    metaEditor: join(brandDir, "MetaEditor64.exe"),
    scriptsDir: join(brandDir, "MQL5", "Scripts"),
    scriptSrcRepo: join(deskRoot(), "mql5", `${SCRIPT_NAME}.mq5`),
    scriptSrcPrefix: join(brandDir, "MQL5", "Scripts", `${SCRIPT_NAME}.mq5`),
    scriptEx5: join(brandDir, "MQL5", "Scripts", `${SCRIPT_NAME}.ex5`),
    bridgeDir,
    accountJson: join(bridgeDir, "account.json"),
    heartbeat: join(bridgeDir, "heartbeat.txt"),
    requestFile: join(bridgeDir, "wsf_desk_order_request.txt"),
    resultFile: join(bridgeDir, "wsf_desk_order_result.json"),
    configIni: join(brandDir, "wsf_desk_order.ini"),
    logsDir: join(brandDir, "logs"),
  };
}

function fileAgeSec(path: string): number | null {
  try {
    return (Date.now() - statSync(path).mtimeMs) / 1000;
  } catch {
    return null;
  }
}

function readBridgeIdentity(accountJson: string): {
  login: string | null;
  server: string | null;
  company: string | null;
  balance: number | null;
} {
  if (!existsSync(accountJson)) {
    return { login: null, server: null, company: null, balance: null };
  }
  try {
    const raw = JSON.parse(readFileSync(accountJson, "utf8")) as Record<string, unknown>;
    return {
      login: raw.login != null ? String(raw.login) : null,
      server: raw.server != null ? String(raw.server) : null,
      company: raw.company != null ? String(raw.company) : null,
      balance: typeof raw.balance === "number" ? raw.balance : null,
    };
  } catch {
    return { login: null, server: null, company: null, balance: null };
  }
}

interface ProcRow {
  pid: number;
  prefix: string;
  cwd: string;
  cmd: string;
}

function listTerminal64(): ProcRow[] {
  const out: ProcRow[] = [];
  let names: string[] = [];
  try {
    names = readdirSync("/proc").filter((n) => /^\d+$/.test(n));
  } catch {
    return out;
  }
  for (const pid of names) {
    try {
      const cmd = readFileSync(`/proc/${pid}/cmdline`).toString("utf8").replace(/\0/g, " ");
      if (!cmd.includes("terminal64.exe") || cmd.includes("bash")) continue;
      let prefix = "";
      try {
        const env = readFileSync(`/proc/${pid}/environ`);
        for (const part of env.toString("utf8").split("\0")) {
          if (part.startsWith("WINEPREFIX=")) {
            prefix = real(part.slice("WINEPREFIX=".length));
            break;
          }
        }
      } catch {
        prefix = "";
      }
      if (!prefix) {
        try {
          const maps = readFileSync(`/proc/${pid}/maps`, "utf8");
          if (maps.includes(".mt5-wsf")) prefix = real(resolveWsfOnlyPrefix());
        } catch {
          prefix = "";
        }
      }
      let cwd = "";
      try {
        cwd = spawnSync("readlink", ["-f", `/proc/${pid}/cwd`], { encoding: "utf8" }).stdout.trim();
      } catch {
        cwd = "";
      }
      out.push({ pid: Number(pid), prefix, cwd, cmd });
    } catch {
      continue;
    }
  }
  return out;
}

function isWsfPrefixRow(row: ProcRow, prefix: string): boolean {
  const blob = `${row.prefix} ${row.cwd} ${row.cmd}`;
  if (blob.includes("Vantage") || blob.includes("FP Markets")) return false;
  if (FORBIDDEN_PREFIX_MARKERS.some((marker) => blob.includes(marker))) return false;
  return row.prefix === prefix;
}

function stopWsfBrandTerminals(prefix: string): number[] {
  const stopped: number[] = [];
  for (const row of listTerminal64()) {
    if (!isWsfPrefixRow(row, prefix)) continue;
    try {
      process.kill(row.pid, "SIGTERM");
      stopped.push(row.pid);
    } catch {
      // already gone
    }
  }
  const deadline = Date.now() + 4000;
  while (Date.now() < deadline) {
    const still = listTerminal64().filter((row) => stopped.includes(row.pid));
    if (still.length === 0) break;
    spawnSync("sleep", ["0.2"]);
  }
  for (const row of listTerminal64()) {
    if (!stopped.includes(row.pid)) continue;
    try {
      process.kill(row.pid, "SIGKILL");
    } catch {
      // gone
    }
  }
  return stopped;
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

function compileScript(paths: ReturnType<typeof wsfPaths>): string | null {
  if (!existsSync(paths.scriptSrcRepo)) {
    return `desk MQL source missing at ${relative(repoRoot(), paths.scriptSrcRepo)}`;
  }
  writeFileSync(paths.scriptSrcPrefix, readFileSync(paths.scriptSrcRepo));
  const needCompile =
    !existsSync(paths.scriptEx5) ||
    statSync(paths.scriptSrcPrefix).mtimeMs > statSync(paths.scriptEx5).mtimeMs;
  if (!needCompile) return null;
  const result = spawnSync(
    "wine",
    [paths.metaEditor, `/compile:${SCRIPT_NAME}.mq5`, "/log"],
    {
      cwd: paths.scriptsDir,
      encoding: "utf8",
      timeout: 40000,
      env: wineEnv(paths.prefix),
    }
  );
  if (!existsSync(paths.scriptEx5)) {
    let hint = result.stderr?.slice(0, 180) || `compile exit ${result.status}`;
    const logPath = join(paths.scriptsDir, `${SCRIPT_NAME}.log`);
    if (existsSync(logPath)) {
      const raw = readFileSync(logPath);
      const text =
        raw[1] === 0
          ? raw.toString("utf16le")
          : raw.toString("utf8");
      const last = text.split(/\r?\n/).filter((l) => l.trim()).slice(-4).join(" | ");
      if (last) hint = last.slice(0, 240);
    }
    return `MetaEditor compile failed: ${hint}`;
  }
  return null;
}

function writeAsciiCrlf(path: string, text: string): void {
  writeFileSync(path, text.replace(/\n/g, "\r\n"), { encoding: "ascii" });
}

function writeRequest(paths: ReturnType<typeof wsfPaths>, parsed: GuardOk, requestId: string): void {
  const body = [
    `request_id=${requestId}`,
    `action=${parsed.action}`,
    `symbol=${parsed.symbol}`,
    `side=${parsed.side}`,
    `confirm=${parsed.confirm}`,
    `volume=${parsed.volume ?? CONSERVATIVE_FX_MIN}`,
    `use_volume_min=${parsed.useVolumeMin ? 1 : 0}`,
    `magic=${WSF_LIVE_MAGIC}`,
    "",
  ].join("\n");
  writeFileSync(paths.requestFile, body, { encoding: "utf8" });
}

function writeStartupIni(paths: ReturnType<typeof wsfPaths>, symbol: string): string | null {
  const text = `[Common]
Login=${WSF_EXPECTED_LOGIN}
Server=WSFmarkets-Server
ProxyEnable=0
KeepPrivate=1
NewsEnable=0
CertInstall=1
[Charts]
MaxBars=100000
PreloadCharts=1
[Experts]
AllowLiveTrading=1
Enabled=1
Account=1
Profile=1
[StartUp]
Script=${SCRIPT_NAME}
Symbol=${symbol}
Period=M1
ShutdownTerminal=1
`;
  if (/password/i.test(text)) return "refusing: password key would be written to ini";
  writeAsciiCrlf(paths.configIni, text);
  return null;
}

function parseResultJson(text: string): Partial<WsfLiveOrderResult> {
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

function readLogText(path: string): string {
  const raw = readFileSync(path);
  if (raw.length >= 2 && raw[1] === 0) return raw.toString("utf16le");
  return raw.toString("utf8");
}

function enrichFromJournal(
  paths: ReturnType<typeof wsfPaths>,
  result: WsfLiveOrderResult
): WsfLiveOrderResult {
  if (!existsSync(paths.logsDir)) return result;
  const today = new Date();
  const stamp = `${today.getFullYear()}${String(today.getMonth() + 1).padStart(2, "0")}${String(today.getDate()).padStart(2, "0")}`;
  const logPath = join(paths.logsDir, `${stamp}.log`);
  if (!existsSync(logPath)) return result;
  let text = "";
  try {
    text = readLogText(logPath);
  } catch {
    return result;
  }
  const needle = result.requestId ? `7desk-${result.requestId}` : "";
  const lines = text.split(/\r?\n/).filter((line) => {
    if (!line.includes("149736") || !/EURUSD/i.test(line)) return false;
    if (needle && line.includes(needle)) return true;
    if (result.order && line.includes(String(result.order))) return true;
    if (/deal #\d+/.test(line)) return true;
    return false;
  });
  const dealRe =
    /deal #(\d+)\s+(buy|sell)\s+([\d.]+)\s+(\S+)\s+at\s+([\d.]+).*order #(\d+)/i;
  const timeRe = /(\d{2}:\d{2}:\d{2}\.\d+)/;
  const deals: Array<{ deal: number; side: string; volume: number; symbol: string; price: number; order: number; time: string }> = [];
  for (const line of lines) {
    const m = line.match(dealRe);
    if (!m) continue;
    deals.push({
      deal: Number(m[1]),
      side: m[2].toUpperCase(),
      volume: Number(m[3]),
      symbol: m[4],
      price: Number(m[5]),
      order: Number(m[6]),
      time: line.match(timeRe)?.[1] || "",
    });
  }
  if (deals.length === 0) return result;
  const open = deals.find((d) => d.side === (result.side || "BUY")) || deals[0];
  const close = [...deals].reverse().find((d) => d !== open) || deals[1];
  const next = { ...result };
  if (open) {
    if (!next.dealOpen) next.dealOpen = open.deal;
    if (!next.openPrice) next.openPrice = open.price;
    if (!next.order) next.order = open.order;
    if (!next.symbol) next.symbol = open.symbol;
    if (!next.volume) next.volume = open.volume;
    next.journalOpen = `${open.time} deal ${open.deal} ${open.side} ${open.volume} ${open.symbol} @ ${open.price}`;
  }
  if (close) {
    if (!next.dealClose) next.dealClose = close.deal;
    if (!next.closePrice) next.closePrice = close.price;
    next.journalClose = `${close.time} deal ${close.deal} ${close.side} ${close.volume} ${close.symbol} @ ${close.price}`;
  }
  return next;
}

function isWsfBrandRow(row: ProcRow, prefix: string): boolean {
  return isWsfPrefixRow(row, prefix) && row.cwd.includes("WSFmarkets MT5 Terminal");
}

function isGenericWsfRow(row: ProcRow, prefix: string): boolean {
  return isWsfPrefixRow(row, prefix) && /\/Program Files\/MetaTrader 5\/?$/.test(row.cwd);
}

function restoreWsfTerminal(paths: ReturnType<typeof wsfPaths>): string {
  const leftover: number[] = [];
  for (const row of listTerminal64()) {
    if (!isGenericWsfRow(row, paths.prefix)) continue;
    try {
      process.kill(row.pid, "SIGTERM");
      leftover.push(row.pid);
    } catch {
      // gone
    }
  }
  const already = listTerminal64().some((row) => isWsfBrandRow(row, paths.prefix));
  if (already) {
    return leftover.length
      ? `WSF brand terminal already running; stopped generic leftover ${leftover.join(",")}`
      : "WSF brand terminal already running";
  }
  const helper = join(repoRoot(), "scripts/21-start-broker-background.sh");
  const child = spawn(helper, ["wsf"], {
    detached: true,
    stdio: "ignore",
  });
  child.unref();
  const extra = leftover.length ? `; stopped generic leftover ${leftover.join(",")}` : "";
  return `restored WSF brand terminal via background helper pid ${child.pid ?? "?"}${extra}`;
}

function newRequestId(): string {
  return `d${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

export async function executeWsfLiveOrder(
  body: WsfLiveOrderInput,
  endpoint = "/api/wsf/order"
): Promise<{ status: number; result: WsfLiveOrderResult }> {
  const requestId = newRequestId();
  const parsed = validateLiveOrderBody(body);
  if (!parsed.ok) {
    parsed.result.requestId = requestId;
    parsed.result.endpoint = endpoint;
    return { status: parsed.status, result: parsed.result };
  }

  const paths = wsfPaths();
  if (paths.prefixError) {
    return { status: 409, result: fail(409, "prefix", paths.prefixError, { requestId, endpoint }).result };
  }
  if (!existsSync(paths.prefix) || !existsSync(paths.terminalExe)) {
    return {
      status: 409,
      result: fail(409, "prefix", "WSF brand terminal is not installed under ~/.mt5-wsf", {
        requestId,
        endpoint,
      }).result,
    };
  }
  if (!existsSync(paths.metaEditor)) {
    return {
      status: 409,
      result: fail(409, "compile", "WSF MetaEditor64.exe missing", { requestId, endpoint }).result,
    };
  }

  const identity = readBridgeIdentity(paths.accountJson);
  if (identity.login !== WSF_EXPECTED_LOGIN) {
    return {
      status: 409,
      result: fail(409, "account", "file-bridge login is not 149736 — refusing OrderSend", {
        requestId,
        endpoint,
        login: identity.login ? Number(identity.login) : null,
        server: identity.server,
      }).result,
    };
  }
  if (!identity.server || !identity.server.includes(WSF_SERVER_NEEDLE)) {
    return {
      status: 409,
      result: fail(409, "account", "file-bridge server is not WSF — refusing OrderSend", {
        requestId,
        endpoint,
        login: Number(identity.login),
        server: identity.server,
      }).result,
    };
  }

  const hbAge = fileAgeSec(paths.heartbeat);
  const accAge = fileAgeSec(paths.accountJson);
  let wsfRunning = listTerminal64().some((row) => isWsfPrefixRow(row, paths.prefix));
  let fresh = (hbAge != null && hbAge < HEARTBEAT_MAX_AGE_SEC) || (accAge != null && accAge < HEARTBEAT_MAX_AGE_SEC);
  if (!fresh && !wsfRunning) {
    restoreWsfTerminal(paths);
    const deadline = Date.now() + 35000;
    while (Date.now() < deadline) {
      spawnSync("sleep", ["0.5"]);
      const next = readBridgeIdentity(paths.accountJson);
      const nextAge = fileAgeSec(paths.accountJson);
      const nextHb = fileAgeSec(paths.heartbeat);
      if (
        next.login === WSF_EXPECTED_LOGIN &&
        ((nextAge != null && nextAge < HEARTBEAT_MAX_AGE_SEC) ||
          (nextHb != null && nextHb < HEARTBEAT_MAX_AGE_SEC))
      ) {
        fresh = true;
        wsfRunning = true;
        break;
      }
    }
  }
  if (!fresh && !wsfRunning) {
    return {
      status: 409,
      result: fail(409, "bridge", "WSF file-bridge snapshot is stale and no WSF terminal is running", {
        requestId,
        endpoint,
        login: identity.login ? Number(identity.login) : null,
        server: identity.server,
      }).result,
    };
  }

  const compileError = compileScript(paths);
  if (compileError) {
    return {
      status: 500,
      result: fail(500, "compile", compileError, {
        requestId,
        endpoint,
        login: Number(identity.login),
        server: identity.server,
      }).result,
    };
  }

  const iniError = writeStartupIni(paths, parsed.symbol);
  if (iniError) {
    return { status: 500, result: fail(500, "ini", iniError, { requestId, endpoint }).result };
  }
  if (existsSync(paths.resultFile)) {
    try {
      unlinkSync(paths.resultFile);
    } catch {
      // ignore
    }
  }
  writeRequest(paths, parsed, requestId);

  const stopped = stopWsfBrandTerminals(paths.prefix);
  const run = spawnSync("wine", ["./terminal64.exe", "/portable", `/config:wsf_desk_order.ini`], {
    cwd: paths.brandDir,
    encoding: "utf8",
    timeout: 90000,
    env: wineEnv(paths.prefix),
  });

  let parsedResult: Partial<WsfLiveOrderResult> = {};
  if (existsSync(paths.resultFile)) {
    parsedResult = parseResultJson(readFileSync(paths.resultFile, "utf8"));
  } else {
    parsedResult = {
      ok: false,
      stage: "timeout",
      reason: `one-shot produced no result (wine status ${run.status}${run.error ? ` ${run.error.message}` : ""})`,
    };
  }

  const base: WsfLiveOrderResult = {
    ok: parsedResult.ok === true,
    source: "seven-desk",
    endpoint,
    requestId,
    stage: parsedResult.stage || "unknown",
    reason: parsedResult.reason || "",
    login: parsedResult.login ?? Number(identity.login),
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
    winePrefix: ".mt5-wsf",
    stoppedWsfPids: stopped,
    restoreNote: "",
  };

  const enriched = enrichFromJournal(paths, base);
  try {
    unlinkSync(paths.configIni);
  } catch {
    // leftover ini is not a secret (login/server only) but drop it anyway
  }
  enriched.restoreNote = restoreWsfTerminal(paths);
  if (enriched.login != null && Number(enriched.login) !== Number(WSF_EXPECTED_LOGIN)) {
    enriched.ok = false;
    enriched.stage = "account";
    enriched.reason = "result login is not 149736";
  }
  const status = enriched.ok ? 200 : enriched.stage === "timeout" ? 504 : 409;
  return { status, result: enriched };
}

export function homeRelativePrefix(): string {
  return join("~", relative(homedir(), resolveWsfOnlyPrefix()) || ".mt5-wsf");
}
