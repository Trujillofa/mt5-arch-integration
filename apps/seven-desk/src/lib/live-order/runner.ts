import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, unlinkSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, relative, resolve } from "node:path";
import {
  LIVE_ORDER_HTTP_BUDGET_MS,
  MIN_LIVE_LOT,
  WINE_ONESHOT_BUDGET_MS,
  asJsonBool,
  classifyOrphanRequest,
  deadlineExceeded,
  disconnectedOrderReason,
  httpTimeoutResult,
  inFlightOrphanReason,
  isUs30Family,
  oneshotChartSymbol,
  parseLiveOrderRequest,
  parseRequestFields,
  quotesPathMatchesSymbol,
  remainingMs,
  resolveStartupServer,
  resultBelongsToRequest,
  resultMatchesRequest,
  withDeadline,
} from "@/lib/live-order/guards";
import { runWineUntil, sleep } from "@/lib/live-order/wine-oneshot";
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
  FORTRADERS_BRAND_INSTALLS,
  FORTRADERS_EXPECTED_LOGIN,
  FORTRADERS_ONLY_PREFIX,
  FORTRADERS_SERVER_NEEDLE,
} from "@/lib/fortraders/env";
import { FORTRADERS_EXPECTED_SERVER, FORTRADERS_LIVE_CONFIRM } from "@/lib/fortraders/types";
import {
  FUNDINGPIPS_BRAND_INSTALLS,
  FUNDINGPIPS_EXPECTED_LOGIN,
  FUNDINGPIPS_ONLY_PREFIX,
  FUNDINGPIPS_SERVER_NEEDLE,
} from "@/lib/fundingpips/env";
import { FUNDINGPIPS_EXPECTED_SERVER, FUNDINGPIPS_LIVE_CONFIRM } from "@/lib/fundingpips/types";
import {
  NEOMAA_BRAND_INSTALLS,
  NEOMAA_EXPECTED_LOGIN,
  NEOMAA_ONLY_PREFIX,
  NEOMAA_SERVER_NEEDLE,
} from "@/lib/neomaa/env";
import { NEOMAA_EXPECTED_SERVER, NEOMAA_LIVE_CONFIRM } from "@/lib/neomaa/types";
import {
  FTMO_BRAND_INSTALLS,
  FTMO_EXPECTED_LOGIN,
  FTMO_ONLY_PREFIX,
  FTMO_SERVER_NEEDLE,
} from "@/lib/ftmo/env";
import { FTMO_EXPECTED_SERVER, FTMO_LIVE_CONFIRM } from "@/lib/ftmo/types";
import type {
  LiveBroker,
  LiveOrderAction,
  LiveOrderInput,
  LiveOrderResult,
  LiveOrderType,
} from "@/lib/live-order/types";

const SCRIPT_NAME = "DeskLiveOrder";
const FORBIDDEN = [".mt5-vantage", ".mt5-fpmarkets", ".mt5-exness"] as const;

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
  fundingpips: {
    id: "fundingpips",
    prefix: FUNDINGPIPS_ONLY_PREFIX,
    brands: FUNDINGPIPS_BRAND_INSTALLS,
    login: FUNDINGPIPS_EXPECTED_LOGIN,
    confirm: FUNDINGPIPS_LIVE_CONFIRM,
    needle: FUNDINGPIPS_SERVER_NEEDLE,
    server: FUNDINGPIPS_EXPECTED_SERVER,
    magic: 20263851,
    defaultSymbol: "EURUSD",
    restoreArg: "fundingpips",
  },
  neomaa: {
    id: "neomaa",
    prefix: NEOMAA_ONLY_PREFIX,
    brands: NEOMAA_BRAND_INSTALLS,
    login: NEOMAA_EXPECTED_LOGIN,
    confirm: NEOMAA_LIVE_CONFIRM,
    needle: NEOMAA_SERVER_NEEDLE,
    server: NEOMAA_EXPECTED_SERVER,
    magic: 20263852,
    defaultSymbol: "EURUSD",
    restoreArg: "neomaa",
  },
  fortraders: {
    id: "fortraders",
    prefix: FORTRADERS_ONLY_PREFIX,
    brands: FORTRADERS_BRAND_INSTALLS,
    login: FORTRADERS_EXPECTED_LOGIN,
    confirm: FORTRADERS_LIVE_CONFIRM,
    needle: FORTRADERS_SERVER_NEEDLE,
    server: FORTRADERS_EXPECTED_SERVER,
    magic: 20263853,
    defaultSymbol: "EURUSD",
    restoreArg: "fortraders",
  },
};

interface GuardOk {
  ok: true;
  action: LiveOrderAction;
  orderType: LiveOrderType;
  symbol: string;
  side: "BUY" | "SELL";
  useVolumeMin: boolean;
  volume: number | null;
  price: number | null;
  sl: number | null;
  tp: number | null;
  ticket: number | null;
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

function validateBody(firm: FirmSpec, body: LiveOrderInput): GuardOk | GuardFail {
  const parsed = parseLiveOrderRequest({
    body,
    expectedConfirm: firm.confirm,
    defaultSymbol: firm.defaultSymbol,
    firmId: firm.id,
  });
  if (!parsed.ok) {
    return fail(firm, parsed.status, parsed.stage, parsed.reason);
  }
  return { ok: true, ...parsed.fields };
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
      if (!quotesPathMatchesSymbol(full, name, want)) {
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

async function stopPrefix(prefix: string): Promise<number[]> {
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
    await sleep(200);
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
    timeout: 20000,
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
    `volume=${parsed.volume ?? MIN_LIVE_LOT}`,
    `use_volume_min=${parsed.useVolumeMin ? 1 : 0}`,
    `order_type=${parsed.orderType}`,
    `price=${parsed.price ?? 0}`,
    `sl=${parsed.sl ?? 0}`,
    `tp=${parsed.tp ?? 0}`,
    `ticket=${parsed.ticket ?? 0}`,
    `magic=${firm.magic}`,
    `issued_at=${Math.floor(Date.now() / 1000)}`,
    "",
  ].join("\n");
  mkdirSync(paths.bridgeDir, { recursive: true });
  writeFileSync(paths.requestFile, body, { encoding: "utf8" });
  for (const dir of paths.extraBridgeDirs) {
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "desk_live_order_request.txt"), body, { encoding: "utf8" });
  }
}

function writeStartupIni(
  firm: FirmSpec,
  paths: ReturnType<typeof pathsFor>,
  symbol: string,
  server: string
): string | null {
  const password = readAutoLoginPassword(paths.autoLogin);
  const common = [
    "[Common]",
    `Login=${firm.login}`,
    `Server=${server}`,
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

function readBridgeIdentity(accountJson: string): {
  login: string | null;
  server: string | null;
  company: string | null;
  terminalConnected: boolean | null;
} {
  if (!existsSync(accountJson)) {
    return { login: null, server: null, company: null, terminalConnected: null };
  }
  try {
    const raw = JSON.parse(readFileSync(accountJson, "utf8")) as Record<string, unknown>;
    return {
      login: raw.login != null ? String(raw.login) : null,
      server: raw.server != null ? String(raw.server) : null,
      company: raw.company != null ? String(raw.company) : null,
      terminalConnected: asJsonBool(raw.terminal_connected),
    };
  } catch {
    return { login: null, server: null, company: null, terminalConnected: null };
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
      orderType: raw.order_type != null ? String(raw.order_type) : undefined,
      price: typeof raw.price === "number" ? raw.price : undefined,
      sl: typeof raw.sl === "number" ? raw.sl : undefined,
      tp: typeof raw.tp === "number" ? raw.tp : undefined,
      order: typeof raw.order === "number" ? raw.order : undefined,
      ticket: typeof raw.ticket === "number" ? raw.ticket : typeof raw.order === "number" ? raw.order : undefined,
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

function requestCandidates(paths: ReturnType<typeof pathsFor>): string[] {
  return [
    paths.requestFile,
    ...paths.extraBridgeDirs.map((dir) => join(dir, "desk_live_order_request.txt")),
  ];
}

function claimCandidates(paths: ReturnType<typeof pathsFor>): string[] {
  return [
    join(paths.bridgeDir, "desk_live_order_claimed.txt"),
    ...paths.extraBridgeDirs.map((dir) => join(dir, "desk_live_order_claimed.txt")),
  ];
}

function unlinkQuiet(path: string): void {
  try {
    unlinkSync(path);
  } catch {
    // gone
  }
}

function dropBridgeFiles(files: string[]): void {
  for (const file of files) {
    if (existsSync(file)) unlinkQuiet(file);
  }
}

function inspectOrphanRequest(paths: ReturnType<typeof pathsFor>): {
  class: ReturnType<typeof classifyOrphanRequest>;
  requestId: string;
} {
  let requestId = "";
  let issuedAt: number | null = null;
  let fileMtimeMs = 0;
  let requestPresent = false;
  for (const file of requestCandidates(paths)) {
    if (!existsSync(file)) continue;
    requestPresent = true;
    const fields = parseRequestFields(readFileSync(file, "utf8"));
    if (fields.requestId) requestId = fields.requestId;
    if (fields.issuedAt != null) issuedAt = fields.issuedAt;
    try {
      fileMtimeMs = statSync(file).mtimeMs;
    } catch {
      fileMtimeMs = 0;
    }
    break;
  }
  if (!requestPresent) {
    for (const file of claimCandidates(paths)) {
      if (!existsSync(file)) continue;
      requestPresent = true;
      const claimed = readFileSync(file, "utf8").trim();
      if (claimed) requestId = claimed;
      try {
        fileMtimeMs = statSync(file).mtimeMs;
      } catch {
        fileMtimeMs = 0;
      }
      break;
    }
  }
  const matchingResult =
    Boolean(requestId) &&
    resultCandidates(paths).some((file) => {
      if (!existsSync(file)) return false;
      const parsed = parseResultJson(readFileSync(file, "utf8"));
      return resultBelongsToRequest(parsed.requestId, requestId);
    });
  const klass = classifyOrphanRequest({
    requestPresent,
    requestId,
    issuedAt,
    fileMtimeMs,
    matchingResult,
  });
  if (klass === "stale" || klass === "done") {
    dropBridgeFiles([...requestCandidates(paths), ...claimCandidates(paths)]);
    if (klass === "stale") dropBridgeFiles(resultCandidates(paths));
  }
  return { class: klass, requestId };
}

function tryReadMatchingResult(
  paths: ReturnType<typeof pathsFor>,
  requestId: string
): Partial<LiveOrderResult> | null {
  for (const resultFile of resultCandidates(paths)) {
    if (!existsSync(resultFile)) continue;
    const parsed = parseResultJson(readFileSync(resultFile, "utf8"));
    if (!resultMatchesRequest(parsed.requestId, requestId)) continue;
    return parsed;
  }
  return null;
}

async function waitResult(
  paths: ReturnType<typeof pathsFor>,
  timeoutMs: number,
  requestId: string
): Promise<Partial<LiveOrderResult>> {
  const deadline = Date.now() + timeoutMs;
  let sawMismatch = false;
  while (Date.now() < deadline) {
    for (const resultFile of resultCandidates(paths)) {
      if (!existsSync(resultFile)) continue;
      const parsed = parseResultJson(readFileSync(resultFile, "utf8"));
      if (!resultMatchesRequest(parsed.requestId, requestId)) {
        sawMismatch = true;
        continue;
      }
      return parsed;
    }
    await sleep(250);
  }
  return {
    ok: false,
    stage: "timeout",
    reason: sawMismatch
      ? "one-shot produced a result for a different request_id"
      : "one-shot produced no result json",
  };
}

function newRequestId(firm: DeskLiveFirm): string {
  return `${firm}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

export interface DeskLiveOrderOptions {
  requestId?: string;
  deadlineMs?: number;
}

export async function executeDeskLiveOrder(
  firmId: DeskLiveFirm,
  body: LiveOrderInput,
  endpoint: string,
  options: DeskLiveOrderOptions = {}
): Promise<{ status: number; result: LiveOrderResult }> {
  const firm = FIRMS[firmId];
  const requestId = options.requestId || newRequestId(firmId);
  const deadlineMs = options.deadlineMs ?? Date.now() + LIVE_ORDER_HTTP_BUDGET_MS;
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
  if (identity.terminalConnected === false) {
    return {
      status: 409,
      result: fail(firm, 409, "connect", disconnectedOrderReason(firm.id, identity.server), {
        requestId,
        endpoint,
        login: identity.login ? Number(identity.login) : null,
        server: identity.server,
      }).result,
    };
  }

  if (deadlineExceeded(deadlineMs) || remainingMs(deadlineMs) < 8000) {
    return {
      status: 504,
      result: fail(firm, 504, "timeout", "live order deadline exhausted before wine one-shot", {
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

  const orphan = inspectOrphanRequest(paths);
  if (orphan.class === "in_flight") {
    return {
      status: 409,
      result: fail(firm, 409, "orphan", inFlightOrphanReason(orphan.requestId), {
        requestId,
        endpoint,
        login: identity.login ? Number(identity.login) : null,
        server: identity.server,
      }).result,
    };
  }

  const needsQuotes =
    !isUs30Family(parsed.symbol) &&
    (firm.id === "fundingpips" ||
      firm.id === "neomaa" ||
      firm.id === "fortraders" ||
      (firm.id === "alphacapital" && !parsed.symbol.toUpperCase().startsWith("BTC")));
  if (needsQuotes && !quotesReady(paths.brandDir, parsed.symbol)) {
    return {
      status: 409,
      result: fail(firm, 409, "symbol", `${parsed.symbol} not synchronized — no history/ticks yet; not sending OrderSend`, {
        requestId,
        endpoint,
        login: identity.login ? Number(identity.login) : null,
        server: identity.server,
      }).result,
    };
  }

  const startupServer = resolveStartupServer(identity.server, firm.server, firm.needle);
  writeStartupIni(firm, paths, oneshotChartSymbol(firm.id, parsed.symbol), startupServer);
  dropBridgeFiles(resultCandidates(paths));
  writeRequest(firm, paths, parsed, requestId);

  let stopped: number[] = [];
  let parsedResult: Partial<LiveOrderResult> = {};
  try {
    stopped = await stopPrefix(firm.prefix);
    const wineDeadline = Math.min(deadlineMs - 2000, Date.now() + WINE_ONESHOT_BUDGET_MS);
    const wine = await runWineUntil({
      cwd: paths.brandDir,
      args: ["./terminal64.exe", "/portable", "/config:desk_live_order.ini"],
      env: wineEnv(firm.prefix),
      deadlineMs: wineDeadline,
      isDone: () => tryReadMatchingResult(paths, requestId) != null,
      onAbort: async () => {
        await stopPrefix(firm.prefix);
      },
    });

    parsedResult =
      tryReadMatchingResult(paths, requestId) ??
      (await waitResult(paths, wine.timedOut ? 400 : 1500, requestId));
    if (!parsedResult.ok && parsedResult.stage === "timeout") {
      if (wine.timedOut) {
        parsedResult.reason =
          "wine one-shot exceeded deadline — no matching result json (orphan request cleaned; no hang without JSON)";
      } else if (wine.exitCode != null) {
        parsedResult.reason = `${parsedResult.reason} (wine status ${wine.exitCode})`;
      }
    }
  } finally {
    await stopPrefix(firm.prefix);
    dropBridgeFiles([...requestCandidates(paths), ...claimCandidates(paths)]);
    unlinkQuiet(paths.configIni);
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
    orderType: parsedResult.orderType ?? parsed.orderType,
    price: parsedResult.price ?? parsed.price ?? undefined,
    sl: parsedResult.sl ?? parsed.sl ?? undefined,
    tp: parsedResult.tp ?? parsed.tp ?? undefined,
    order: parsedResult.order,
    ticket: parsedResult.ticket ?? parsedResult.order,
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
    const firm = FIRMS[firmId];
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
          winePrefix: winePrefixLabel(firm.prefix),
        },
        { status: 400 }
      );
    }
    const payload = body && typeof body === "object" ? (body as Record<string, unknown>) : {};
    const requestId = newRequestId(firmId);
    const deadlineMs = Date.now() + LIVE_ORDER_HTTP_BUDGET_MS;
    try {
      const { status, result } = await withDeadline(
        executeDeskLiveOrder(
          firmId,
          {
            live: payload.live,
            confirm: payload.confirm,
            action: forceAction ?? payload.action,
            order_type: payload.order_type,
            symbol: payload.symbol,
            side: payload.side,
            volume: payload.volume,
            volume_min: payload.volume_min,
            volume_confirm: payload.volume_confirm,
            price: payload.price,
            sl: payload.sl,
            tp: payload.tp,
            ticket: payload.ticket,
            order: payload.order,
          },
          endpoint,
          { requestId, deadlineMs }
        ),
        LIVE_ORDER_HTTP_BUDGET_MS,
        {
          status: 504,
          result: httpTimeoutResult({
            endpoint,
            requestId,
            winePrefix: winePrefixLabel(firm.prefix),
          }),
        }
      );
      return Response.json(result, { status });
    } catch (caught) {
      return Response.json(
        fail(
          firm,
          500,
          "error",
          caught instanceof Error ? caught.message : "live order failed",
          { requestId, endpoint }
        ).result,
        { status: 500 }
      );
    }
  };
}
