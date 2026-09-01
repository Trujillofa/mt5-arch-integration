import {
  WSF_CTRADER_BROKER,
  WSF_CTRADER_ID,
  WSF_CTRADER_ID_ACCOUNTS,
  WSF_CTRADER_ID_LOGIN,
  WSF_CTRADER_WEB,
  WSF_HOME,
  WSF_ID_APP,
  WSF_ID_APP_ACCOUNTS,
  WSF_ID_APP_LOGIN,
  WSF_MATCHTRADER_BROKER_ID,
  WSF_MATCHTRADER_LOGIN,
  WSF_MATCHTRADER_WEB,
  WSF_MT5_INSTALLER,
  WSF_MT5_PUBLIC_LOGIN,
  WSF_MT5_SERVER,
  WSF_PORTAL,
  WSF_PUBLIC_DEMO_EMAIL,
  WSF_SPOTWARE_CONNECT_ACCOUNTS,
  WSF_USER_AGENT,
} from "@/lib/wsf/contract";
import { operatorEnvPresent, readOperatorEnv, winePrefixExists } from "@/lib/wsf/env";
import { probeMt5ArchCli } from "@/lib/wsf/mt5-arch-cli";
import { readMt5FileBackend } from "@/lib/wsf/mt5-file-backend";
import type {
  WsfConnectionStatus,
  WsfDealRow,
  WsfFetchedAccount,
  WsfLiveReport,
  WsfPlatformProbe,
  WsfPositionRow,
} from "@/lib/wsf/types";

export type {
  WsfDealRow,
  WsfFetchedAccount,
  WsfIdentity,
  WsfLiveReport,
  WsfPlatformProbe,
  WsfPositionRow,
} from "@/lib/wsf/types";

interface OfficialCard {
  email: string;
  password: string;
  mt5Login: string;
  mt5Server: string;
  mt5Password: string;
}

interface CtidSession {
  authenticated: boolean;
  httpStatus: number | null;
  cookies: string[];
  location: string;
  detail: string;
}

function headers(extra?: HeadersInit): HeadersInit {
  return { "User-Agent": WSF_USER_AGENT, Accept: "text/html,application/json", ...extra };
}

function readSetCookies(response: Response): string[] {
  const responseHeaders = response.headers as Headers & { getSetCookie?: () => string[] };
  if (typeof responseHeaders.getSetCookie === "function") {
    return responseHeaders.getSetCookie();
  }
  const single = response.headers.get("set-cookie");
  return single ? [single] : [];
}

function mergeCookies(...groups: string[][]): string[] {
  const map = new Map<string, string>();
  for (const group of groups) {
    for (const entry of group) {
      const pair = entry.split(";")[0]?.trim();
      if (!pair || !pair.includes("=")) continue;
      map.set(pair.slice(0, pair.indexOf("=")), pair);
    }
  }
  return [...map.values()];
}

function cookieHeader(setCookie: string[]): string {
  return setCookie
    .map((entry) => entry.split(";")[0])
    .filter(Boolean)
    .join("; ");
}

function maskEmail(email: string): string {
  const [user, domain] = email.split("@");
  if (!domain) return "***";
  const shown = user.slice(0, 2);
  return `${shown}***@${domain}`;
}

function decodeEntities(value: string): string {
  return value
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&#(\d+);/g, (_, code) => String.fromCharCode(Number(code)));
}

function parseMoney(raw: string): number | null {
  const cleaned = raw.replace(/,/g, "").trim();
  if (!cleaned) return null;
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

function envOverride(): Partial<OfficialCard> {
  const operator = readOperatorEnv();
  return {
    email: process.env.WSF_DEMO_EMAIL || operator.email || undefined,
    password: process.env.WSF_DEMO_PASSWORD || undefined,
    mt5Login: operator.mt5Login || undefined,
    mt5Password: process.env.WSF_MT5_PASSWORD || process.env.MT5_PASSWORD || undefined,
    mt5Server: operator.mt5Server || undefined,
  };
}

export async function fetchOfficialDemoCard(): Promise<{
  card: OfficialCard | null;
  homepageOk: boolean;
}> {
  try {
    const response = await fetch(WSF_HOME, {
      headers: headers(),
      cache: "no-store",
      redirect: "follow",
    });
    if (!response.ok) return { card: null, homepageOk: false };
    const html = await response.text();
    const mt5 = html.match(
      /Login:\s*(\d+)[\s\S]{0,80}Password:\s*([^<\s]+)[\s\S]{0,80}Server:\s*([A-Za-z0-9._-]+)/i
    );
    const match = html.match(
      /Matchtrader[\s\S]{0,400}Username:\s*([^<\s]+)[\s\S]{0,80}Password:\s*([^<\s]+)/i
    );
    const card: OfficialCard = {
      email: match?.[1] || WSF_PUBLIC_DEMO_EMAIL,
      password: match?.[2] || "",
      mt5Login: mt5?.[1] || WSF_MT5_PUBLIC_LOGIN,
      mt5Password: mt5?.[2] || "",
      mt5Server: mt5?.[3] || WSF_MT5_SERVER,
    };
    const override = envOverride();
    return {
      homepageOk: true,
      card: {
        ...card,
        ...Object.fromEntries(
          Object.entries(override).filter(([, value]) => Boolean(value))
        ),
      } as OfficialCard,
    };
  } catch {
    const override = envOverride();
    if (override.email && override.password) {
      return {
        homepageOk: false,
        card: {
          email: override.email,
          password: override.password,
          mt5Login: override.mt5Login || WSF_MT5_PUBLIC_LOGIN,
          mt5Password: override.mt5Password || "",
          mt5Server: override.mt5Server || WSF_MT5_SERVER,
        },
      };
    }
    return { card: null, homepageOk: false };
  }
}

function loginSucceeded(status: number, location: string): boolean {
  const dest = location.toLowerCase();
  if (dest.includes("/login")) return false;
  if (status >= 300 && status < 400 && dest.length > 0) return true;
  if (status === 200 && dest.includes("/my/")) return true;
  return false;
}

async function loginCtidHost(
  origin: string,
  loginUrl: string,
  email: string,
  password: string
): Promise<CtidSession> {
  const page = await fetch(origin + "/", {
    headers: headers(),
    redirect: "follow",
    cache: "no-store",
  });
  const html = await page.text();
  const token = html.match(/name="_token"\s+value="([^"]+)"/)?.[1];
  if (!token) {
    return {
      authenticated: false,
      httpStatus: page.status,
      cookies: [],
      location: "",
      detail: `${origin} loaded but CSRF token was missing.`,
    };
  }

  const cookies = mergeCookies(readSetCookies(page));
  const login = await fetch(loginUrl, {
    method: "POST",
    headers: {
      ...headers({
        "Content-Type": "application/x-www-form-urlencoded",
        Origin: origin,
        Referer: origin + "/",
        Cookie: cookieHeader(cookies),
      }),
    },
    body: new URLSearchParams({
      _token: token,
      id: email,
      password,
      remember: "1",
    }),
    redirect: "manual",
    cache: "no-store",
  });
  const location = login.headers.get("location") ?? "";
  const nextCookies = mergeCookies(cookies, readSetCookies(login));
  const authenticated = loginSucceeded(login.status, location);
  return {
    authenticated,
    httpStatus: login.status,
    cookies: nextCookies,
    location,
    detail: authenticated
      ? `Session accepted at ${origin} (HTTP ${login.status}${location ? ` → ${location}` : ""}).`
      : `Login at ${origin} returned HTTP ${login.status}${location ? ` → ${location}` : ""}.`,
  };
}

export function parseCtidNickname(html: string): string | null {
  const nick =
    html.match(/id="nickname-top-bar"[^>]*>\s*([^<]+)/)?.[1]?.trim() ||
    html.match(/id="profile-nickname">\s*([^<]+)/)?.[1]?.trim() ||
    html.match(/\b(ctid\d+)\b/)?.[1] ||
    null;
  return nick || null;
}

function mergeBooks(...groups: WsfFetchedAccount[][]): WsfFetchedAccount[] {
  const map = new Map<string, WsfFetchedAccount>();
  for (const group of groups) {
    for (const book of group) {
      const key = `${book.broker}:${book.login}`;
      const existing = map.get(key);
      if (!existing) {
        map.set(key, book);
        continue;
      }
      map.set(key, {
        ...existing,
        ...book,
        balance: book.balance ?? existing.balance,
        equity: book.equity ?? existing.equity,
        currency: book.currency ?? existing.currency,
        leverage: book.leverage ?? existing.leverage,
      });
    }
  }
  return [...map.values()];
}

export function parseCtidAccounts(
  html: string,
  source: WsfFetchedAccount["source"],
  kind: WsfFetchedAccount["kind"]
): WsfFetchedAccount[] {
  const books: WsfFetchedAccount[] = [];
  const chunks = html.split(/id="brokerName">/);
  for (const chunk of chunks.slice(1)) {
    const broker = decodeEntities(chunk.match(/^([^<]+)/)?.[1]?.trim() || "Unknown");
    const rows = chunk.matchAll(
      /id="account(\d+)"[\s\S]{0,400}?<span>([^<]+)<\/span>/g
    );
    for (const row of rows) {
      const accountId = row[1];
      const label = decodeEntities(row[2]).replace(/\s+/g, " ").trim();
      const parsed = label.match(
        /^(Demo|Live)\s*-\s*(.+?)\s*-\s*(\d+)\s*-\s*([\d,.]+)\s*([A-Z]{3})\s*-\s*(1:\d+)/i
      );
      const environment =
        parsed?.[1]?.toLowerCase() === "live"
          ? "live"
          : parsed?.[1]?.toLowerCase() === "demo"
            ? "demo"
            : "unknown";
      const balance = parsed ? parseMoney(parsed[4]) : null;
      const plantIsWsf = /wsf|wall\s*street\s*funded/i.test(broker);
      books.push({
        source,
        kind: plantIsWsf ? "wsf-plant" : kind,
        broker,
        accountId,
        login: parsed?.[3] || accountId,
        name: label,
        environment,
        accountType: parsed?.[2]?.trim() || null,
        balance,
        equity: balance,
        currency: parsed?.[5] || null,
        leverage: parsed?.[6] || null,
        plantIsWsf,
      });
    }
  }
  return books;
}

async function fetchAuthedHtml(
  url: string,
  cookies: string[]
): Promise<{ ok: boolean; status: number; html: string }> {
  const response = await fetch(url, {
    headers: {
      ...headers(),
      Cookie: cookieHeader(cookies),
    },
    redirect: "follow",
    cache: "no-store",
  });
  const html = await response.text();
  const bounced = /\/login\b/i.test(response.url) && !/\/my\//i.test(response.url);
  return { ok: response.ok && !bounced, status: response.status, html };
}

interface ConnectAccount {
  accountId?: number | string;
  accountNumber?: number | string;
  brokerName?: string;
  brokerTitle?: string;
  depositCurrency?: string;
  balance?: number;
  leverage?: number;
  live?: boolean;
  traderAccountType?: string;
}

async function fetchConnectHistory(accessToken: string): Promise<{
  books: WsfFetchedAccount[];
  positions: WsfPositionRow[];
  deals: WsfDealRow[];
  note: string;
}> {
  const url = `${WSF_SPOTWARE_CONNECT_ACCOUNTS}?access_token=${encodeURIComponent(accessToken)}`;
  const response = await fetch(url, {
    headers: headers({ Accept: "application/json" }),
    cache: "no-store",
  });
  const text = await response.text();
  if (!response.ok) {
    return {
      books: [],
      positions: [],
      deals: [],
      note: `Spotware Connect with env token returned HTTP ${response.status}. Token not printed.`,
    };
  }
  const parsed = JSON.parse(text) as { data?: ConnectAccount[] };
  const rows = parsed.data ?? [];
  const books: WsfFetchedAccount[] = rows.map((row) => {
    const broker = row.brokerTitle || row.brokerName || "Unknown";
    const login = String(row.accountNumber ?? row.accountId ?? "");
    return {
      source: "ctrader-id",
      kind: /wsf|wall\s*street\s*funded/i.test(broker) ? "wsf-plant" : "published-demo",
      broker,
      accountId: String(row.accountId ?? login),
      login,
      name: `${row.live ? "Live" : "Demo"} ${row.traderAccountType || ""}`.trim(),
      environment: row.live ? "live" : "demo",
      accountType: row.traderAccountType || null,
      balance: typeof row.balance === "number" ? row.balance : null,
      equity: typeof row.balance === "number" ? row.balance : null,
      currency: row.depositCurrency || null,
      leverage: row.leverage ? `1:${row.leverage}` : null,
      plantIsWsf: /wsf|wall\s*street\s*funded/i.test(broker),
    };
  });

  const positions: WsfPositionRow[] = [];
  const deals: WsfDealRow[] = [];
  for (const row of rows.slice(0, 6)) {
    const id = row.accountId;
    if (id == null) continue;
    const login = String(row.accountNumber ?? id);
    const [posRes, dealRes] = await Promise.all([
      fetch(
        `https://api.spotware.com/connect/tradingaccounts/${id}/positions?access_token=${encodeURIComponent(accessToken)}`,
        { headers: headers({ Accept: "application/json" }), cache: "no-store" }
      ),
      fetch(
        `https://api.spotware.com/connect/tradingaccounts/${id}/deals?access_token=${encodeURIComponent(accessToken)}`,
        { headers: headers({ Accept: "application/json" }), cache: "no-store" }
      ),
    ]);
    if (posRes.ok) {
      const body = (await posRes.json()) as {
        data?: Array<{
          symbolName?: string;
          tradeSide?: string;
          volume?: number;
          entryPrice?: number;
          unrealizedGrossProfit?: number;
        }>;
      };
      for (const pos of body.data ?? []) {
        positions.push({
          accountLogin: login,
          symbol: pos.symbolName || "unknown",
          side: pos.tradeSide || "unknown",
          volume: pos.volume ?? null,
          entry: pos.entryPrice ?? null,
          pnl: pos.unrealizedGrossProfit ?? null,
        });
      }
    }
    if (dealRes.ok) {
      const body = (await dealRes.json()) as {
        data?: Array<{
          symbolName?: string;
          tradeSide?: string;
          volume?: number;
          executionPrice?: number;
          executionTimestamp?: number;
        }>;
      };
      for (const deal of (body.data ?? []).slice(0, 20)) {
        deals.push({
          accountLogin: login,
          symbol: deal.symbolName || "unknown",
          side: deal.tradeSide || "unknown",
          volume: deal.volume ?? null,
          price: deal.executionPrice ?? null,
          time: deal.executionTimestamp
            ? new Date(deal.executionTimestamp).toISOString()
            : null,
        });
      }
    }
  }

  return {
    books,
    positions,
    deals,
    note: `Spotware Connect token accepted. ${books.length} book(s), ${positions.length} position(s), ${deals.length} deal(s).`,
  };
}

async function probeConnectHistory(accountIds: string[]): Promise<{
  books: WsfFetchedAccount[];
  positions: WsfPositionRow[];
  deals: WsfDealRow[];
  note: string;
}> {
  const token = process.env.CTRADER_ACCESS_TOKEN;
  if (token) {
    try {
      return await fetchConnectHistory(token);
    } catch (error) {
      return {
        books: [],
        positions: [],
        deals: [],
        note:
          error instanceof Error
            ? `Spotware Connect token path failed: ${error.message}`
            : "Spotware Connect token path failed.",
      };
    }
  }
  try {
    const response = await fetch(WSF_SPOTWARE_CONNECT_ACCOUNTS, {
      headers: headers({ Accept: "application/json" }),
      cache: "no-store",
    });
    const text = await response.text();
    let code = "";
    try {
      const parsed = JSON.parse(text) as { error?: { errorCode?: string } };
      code = parsed.error?.errorCode || "";
    } catch {
      code = "";
    }
    return {
      books: [],
      positions: [],
      deals: [],
      note: `Spotware Connect HTTP ${response.status}${code ? ` (${code})` : ""} — positions/deals need an Open API oauth_token. No CTRADER_ACCESS_TOKEN in env. Skipped ${accountIds.length} account id(s).`,
    };
  } catch (error) {
    return {
      books: [],
      positions: [],
      deals: [],
      note:
        error instanceof Error
          ? `Spotware Connect unreachable: ${error.message}`
          : "Spotware Connect unreachable.",
    };
  }
}

async function probeMetaApiAccounts(): Promise<{
  books: WsfFetchedAccount[];
  note: string;
}> {
  const token = process.env.METAAPI_TOKEN;
  if (!token) {
    return {
      books: [],
      note: "No METAAPI_TOKEN in env — operator MT5 history was not fetched via MetaAPI.",
    };
  }
  try {
    const response = await fetch(
      "https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai/users/current/accounts",
      {
        headers: headers({
          Accept: "application/json",
          "auth-token": token,
        }),
        cache: "no-store",
      }
    );
    if (!response.ok) {
      return {
        books: [],
        note: `MetaAPI account list HTTP ${response.status}. Token not printed.`,
      };
    }
    const rows = (await response.json()) as Array<{
      login?: string;
      name?: string;
      server?: string;
      _id?: string;
    }>;
    const list = Array.isArray(rows) ? rows : [];
    return {
      books: list.map((row) => ({
        source: "mt5-public-card" as const,
        kind: /wsf/i.test(row.server || row.name || "")
          ? ("wsf-plant" as const)
          : ("public-identifier" as const),
        broker: row.server || "MetaAPI",
        accountId: row._id || row.login || "unknown",
        login: String(row.login || row._id || ""),
        name: row.name || String(row.login || "MetaAPI account"),
        environment: "unknown" as const,
        accountType: null,
        balance: null,
        equity: null,
        currency: null,
        leverage: null,
        plantIsWsf: /wsf/i.test(row.server || ""),
      })),
      note: `MetaAPI listed ${list.length} account(s). Token not printed.`,
    };
  } catch (error) {
    return {
      books: [],
      note:
        error instanceof Error
          ? `MetaAPI list failed: ${error.message}`
          : "MetaAPI list failed.",
    };
  }
}

async function probeMt5Installer(
  login: string,
  server: string,
  hasPassword: boolean
): Promise<WsfPlatformProbe> {
  const personal = login !== WSF_MT5_PUBLIC_LOGIN;
  try {
    const response = await fetch(WSF_MT5_INSTALLER, {
      method: "HEAD",
      headers: headers(),
      redirect: "follow",
    });
    return {
      platform: "mt5",
      endpoint: WSF_MT5_INSTALLER,
      httpStatus: response.status,
      reachable: response.ok,
      authenticated: hasPassword ? false : null,
      publicLogin: login,
      publicServer: server,
      detail: response.ok
        ? personal
          ? `WSF MT5 installer reachable. Operator login ${login} @ ${server} is loaded from env.${
              hasPassword
                ? " A password is present but binary MT5 login needs MetaAPI or a file-backend snapshot — not performed."
                : " No password/token/file snapshot — live balance was not fetched. Paper fallback stays on."
            }`
          : "Official WSF Markets Ltd MT5 installer is reachable. Binary MT5 login needs a terminal or MetaAPI token — not performed."
        : `Installer HEAD returned ${response.status}.`,
    };
  } catch (error) {
    return {
      platform: "mt5",
      endpoint: WSF_MT5_INSTALLER,
      httpStatus: null,
      reachable: false,
      authenticated: null,
      publicLogin: login,
      publicServer: server,
      detail: error instanceof Error ? error.message : "MT5 installer unreachable.",
    };
  }
}

async function probeCTraderId(
  email: string,
  password: string
): Promise<{
  probe: WsfPlatformProbe;
  books: WsfFetchedAccount[];
  nickname: string | null;
  notes: string[];
}> {
  const web = await fetch(WSF_CTRADER_WEB, {
    headers: headers(),
    redirect: "follow",
  })
    .then((response) => ({ ok: response.ok, status: response.status }))
    .catch(() => ({ ok: false, status: null as number | null }));

  if (!password) {
    return {
      probe: {
        platform: "ctrader",
        endpoint: WSF_CTRADER_ID_LOGIN,
        httpStatus: web.status,
        reachable: web.ok,
        authenticated: false,
        detail: `cTrader web ${web.ok ? "up" : "down"} (broker=${WSF_CTRADER_BROKER}). No password available for id.ctrader.com login.`,
      },
      books: [],
      nickname: null,
      notes: [],
    };
  }

  try {
    const session = await loginCtidHost(
      WSF_CTRADER_ID,
      WSF_CTRADER_ID_LOGIN,
      email,
      password
    );
    const notes: string[] = [];
    let books: WsfFetchedAccount[] = [];
    let nickname: string | null = null;
    let authenticated = session.authenticated;

    const accounts = await fetchAuthedHtml(WSF_CTRADER_ID_ACCOUNTS, session.cookies);
    if (accounts.ok) {
      nickname = parseCtidNickname(accounts.html);
      books = parseCtidAccounts(accounts.html, "ctrader-id", "published-demo");
      if (nickname || books.length) authenticated = true;
      notes.push(
        `Fetched ${books.length} trading book(s) from ${WSF_CTRADER_ID_ACCOUNTS} after cTrader ID login.`
      );
    } else if (authenticated) {
      notes.push(`Authenticated, but accounts page returned HTTP ${accounts.status}.`);
    }

    return {
      probe: {
        platform: "ctrader",
        endpoint: WSF_CTRADER_ID_LOGIN,
        httpStatus: session.httpStatus,
        reachable: true,
        authenticated,
        detail: authenticated
          ? `cTrader ID accepted the session (read-only). ${books.length} book(s) fetched from /my/settings/accounts. Web terminal ${web.ok ? "is up" : "did not load"}.`
          : `${session.detail} Web terminal ${web.ok ? "is up" : "did not load"}.`,
      },
      books,
      nickname,
      notes,
    };
  } catch (error) {
    return {
      probe: {
        platform: "ctrader",
        endpoint: WSF_CTRADER_ID_LOGIN,
        httpStatus: web.status,
        reachable: web.ok,
        authenticated: false,
        detail: error instanceof Error ? error.message : "cTrader ID probe failed.",
      },
      books: [],
      nickname: null,
      notes: [],
    };
  }
}

async function fetchWsfPlantBooks(
  email: string,
  password: string
): Promise<{ books: WsfFetchedAccount[]; notes: string[]; authenticated: boolean }> {
  if (!password) {
    return { books: [], notes: [], authenticated: false };
  }
  try {
    const session = await loginCtidHost(WSF_ID_APP, WSF_ID_APP_LOGIN, email, password);
    if (!session.authenticated) {
      return { books: [], notes: [session.detail], authenticated: false };
    }
    const accounts = await fetchAuthedHtml(WSF_ID_APP_ACCOUNTS, session.cookies);
    if (!accounts.ok) {
      return {
        books: [],
        notes: [`WSF id-app authenticated, accounts page HTTP ${accounts.status}.`],
        authenticated: true,
      };
    }
    const books = parseCtidAccounts(accounts.html, "wsf-id-app", "wsf-plant");
    const empty = /no trading accounts yet/i.test(accounts.html);
    return {
      books,
      authenticated: true,
      notes: [
        empty
          ? "WSF-branded id-app.wsfunded.com accepted the same cTID and lists zero WSF-plant trading accounts."
          : `WSF id-app returned ${books.length} plant book(s).`,
      ],
    };
  } catch (error) {
    return {
      books: [],
      authenticated: false,
      notes: [
        error instanceof Error
          ? `WSF id-app fetch failed: ${error.message}`
          : "WSF id-app fetch failed.",
      ],
    };
  }
}

async function probeMatchTrader(email: string, password: string): Promise<WsfPlatformProbe> {
  try {
    const page = await fetch(WSF_MATCHTRADER_WEB + "/", {
      headers: headers(),
      redirect: "follow",
    });
    const text = await page.text();
    const challenged =
      page.status === 403 || /just a moment|cf-mitigated|cloudflare/i.test(text);

    if (!password) {
      return {
        platform: "match-trader",
        endpoint: WSF_MATCHTRADER_WEB,
        httpStatus: page.status,
        reachable: page.ok,
        authenticated: false,
        detail: challenged
          ? "Match-Trader host is behind a Cloudflare challenge. No password to retry login."
          : `Match-Trader web returned ${page.status}.`,
      };
    }

    const login = await fetch(WSF_MATCHTRADER_LOGIN, {
      method: "POST",
      headers: headers({
        Accept: "application/json",
        "Content-Type": "application/json",
        Origin: WSF_MATCHTRADER_WEB,
        Referer: WSF_MATCHTRADER_WEB + "/",
      }),
      body: JSON.stringify({
        email,
        password,
        brokerId: WSF_MATCHTRADER_BROKER_ID,
      }),
    });
    const body = await login.text();
    const loginChallenged =
      login.status === 403 && /just a moment|cloudflare|cf-ray/i.test(body);
    type MatchLogin = { token?: string; accounts?: unknown[]; error?: string };
    let parsed: MatchLogin | null = null;
    try {
      parsed = JSON.parse(body) as MatchLogin;
    } catch {
      parsed = null;
    }

    return {
      platform: "match-trader",
      endpoint: WSF_MATCHTRADER_LOGIN,
      httpStatus: login.status,
      reachable: !loginChallenged,
      authenticated: Boolean(parsed?.token),
      detail: loginChallenged
        ? "Match-Trader /manager/co-login is blocked by Cloudflare from this host. Official web URL is prop.wsfunded.com (Match-Trader Platform API)."
        : parsed?.token
          ? `Match-Trader login succeeded for brokerId=${WSF_MATCHTRADER_BROKER_ID}. Token received; no orders placed.`
          : login.status === 401
            ? "Match-Trader API is reachable (auth-mtr oauth/token). Official homepage demo card is rejected — need a Match-Trader-issued password, not the cTrader ID demo."
            : `Match-Trader login HTTP ${login.status}${parsed?.error ? `: ${parsed.error}` : ""}.`,
    };
  } catch (error) {
    return {
      platform: "match-trader",
      endpoint: WSF_MATCHTRADER_LOGIN,
      httpStatus: null,
      reachable: false,
      authenticated: false,
      detail: error instanceof Error ? error.message : "Match-Trader probe failed.",
    };
  }
}

function personalMt5Book(
  login: string,
  server: string,
  snapshot: ReturnType<typeof readMt5FileBackend>
): WsfFetchedAccount {
  if (snapshot.book) return snapshot.book;
  return {
    source: "mt5-env",
    kind: "personal-env",
    broker: server,
    accountId: login,
    login,
    name: `WSF MT5 ${login}`,
    environment: "unknown",
    accountType: null,
    balance: null,
    equity: null,
    currency: null,
    leverage: null,
    plantIsWsf: true,
  };
}

export async function probeWsfLive(): Promise<WsfLiveReport> {
  const operator = readOperatorEnv();
  const useOperator = operatorEnvPresent(operator);
  const { card, homepageOk } = useOperator
    ? { card: null, homepageOk: false }
    : await fetchOfficialDemoCard();

  const email = useOperator ? operator.email : card?.email || WSF_PUBLIC_DEMO_EMAIL;
  const password = useOperator ? "" : card?.password || "";
  const usedOfficialDemoCard = !useOperator && Boolean(card?.password) && !process.env.WSF_DEMO_PASSWORD;
  const mt5Login = operator.mt5Login || card?.mt5Login || WSF_MT5_PUBLIC_LOGIN;
  const mt5Server = operator.mt5Server || card?.mt5Server || WSF_MT5_SERVER;

  const fileSnap = readMt5FileBackend(operator);
  const archCli = probeMt5ArchCli();

  const [mt5, ctrader, matchTrader, plant] = await Promise.all([
    probeMt5Installer(mt5Login, mt5Server, operator.hasMt5Password),
    useOperator
      ? Promise.resolve({
          probe: {
            platform: "ctrader" as const,
            endpoint: WSF_CTRADER_ID_LOGIN,
            httpStatus: null,
            reachable: false,
            authenticated: false,
            detail:
              "Operator MT5 env is present — skipped the public homepage cTrader demo card.",
          },
          books: [] as WsfFetchedAccount[],
          nickname: null,
          notes: [
            "Did not log into the published WSF demo cTID. Operator credentials are MT5 login/server only.",
          ],
        })
      : probeCTraderId(email || "", password),
    useOperator
      ? Promise.resolve({
          platform: "match-trader" as const,
          endpoint: WSF_MATCHTRADER_LOGIN,
          httpStatus: null,
          reachable: true,
          authenticated: false,
          detail:
            "Skipped Match-Trader homepage demo login. Uploaded env has no Match-Trader password.",
        })
      : probeMatchTrader(email || "", password),
    useOperator
      ? Promise.resolve({
          books: [] as WsfFetchedAccount[],
          notes: [
            "Skipped WSF id-app demo login. No cTrader password in the operator env.",
          ],
          authenticated: false,
        })
      : fetchWsfPlantBooks(email || "", password),
  ]);

  if (useOperator) {
    mt5.reachable = mt5.reachable || mt5.httpStatus === 200;
  }

  const connect = useOperator
    ? {
        books: [] as WsfFetchedAccount[],
        positions: [] as WsfPositionRow[],
        deals: [] as WsfDealRow[],
        note: "Skipped Spotware Connect demo path. No CTRADER_ACCESS_TOKEN in operator env.",
      }
    : await probeConnectHistory(
        [...ctrader.books, ...plant.books].map((book) => book.accountId)
      );
  const meta = await probeMetaApiAccounts();
  const operatorBook = useOperator
    ? [personalMt5Book(mt5Login, mt5Server, fileSnap)]
    : [];
  const books = mergeBooks(
    operatorBook,
    fileSnap.book ? [fileSnap.book] : [],
    archCli.book ? [archCli.book] : [],
    ctrader.books,
    plant.books,
    connect.books,
    meta.books
  );
  const openPositions = [...fileSnap.positions, ...archCli.positions, ...connect.positions];
  const recentDeals = [...fileSnap.deals, ...archCli.deals, ...connect.deals];
  const fetchNotes = [
    useOperator
      ? `Operator env loaded: MT5 login ${mt5Login} @ ${mt5Server}. Password ${
          operator.hasMt5Password ? "present (not shown)" : "missing from uploaded file"
        }. Backend ${operator.mt5Backend || "unset"}.`
      : "No operator MT5 env — using public homepage demo card.",
    fileSnap.note,
    archCli.note,
    ...ctrader.notes,
    ...plant.notes,
    connect.note,
    meta.note,
    openPositions.length || recentDeals.length
      ? `History fetch: ${openPositions.length} open position(s), ${recentDeals.length} recent deal(s).`
      : fileSnap.book || archCli.book
        ? "Live snapshot is present; the WSF book currently has no open positions or recent deals."
        : operator.hasMt5Password
        ? "No live positions or deals. Password is loaded; this host has no Wine/Mt5ArchBridge snapshot and no METAAPI_TOKEN."
        : "No live positions or deals. Need MT5 password + MetaAPI, a file-backend snapshot from the logged-in terminal, or CTRADER_ACCESS_TOKEN.",
    "No orders were placed. Paper adapter remains the execution path.",
  ];

  const winePrefixPresent = winePrefixExists(operator);
  const fileBridgePresent = Boolean(fileSnap.book && fileSnap.book.balance != null);
  const liveBalance =
    books.find((book) => book.source === "mt5-env" && book.balance != null) ||
    books.find((book) => book.kind === "personal-env" && book.balance != null);
  const snapshotLogin = liveBalance?.login || fileSnap.book?.login || archCli.book?.login || mt5Login;
  const snapshotServer =
    liveBalance?.broker || fileSnap.book?.broker || archCli.book?.broker || mt5Server;
  const bookHonesty = useOperator
    ? liveBalance
      ? `Operator WSF MT5 book ${mt5Login} @ ${mt5Server}. Live snapshot came from ${
          fileSnap.book ? "the Mt5ArchBridge file backend" : "MetaAPI"
        }. Challenge vs funded is not labeled by WSF in this feed — treat it as the operator’s own plant login, not the public 4013 demo.`
      : operator.hasMt5Password
        ? `Operator WSF MT5 login ${mt5Login} @ ${mt5Server}: master password is loaded from gitignored env (not shown). This host has no Wine prefix / Mt5ArchBridge snapshot, so balance, positions, and deals were not fetched. The MT5 password was not sent to cTrader or Match-Trader. Desk stays on paper until the Arch Wine terminal is writing account.json, or a METAAPI_TOKEN is provided.`
        : `Operator WSF MT5 login ${mt5Login} @ ${mt5Server} is loaded from env (not the public 4013 demo). Password is still missing, so live books were not fetched.`
    : usedOfficialDemoCard
      ? "This is WSF’s published homepage demo cTID, not a personal funded challenge."
      : "No operator or homepage credentials were available.";

  const nextSecretNeeded = useOperator
    ? liveBalance
      ? null
      : operator.hasMt5Password
        ? `A running ~/.mt5-wsf terminal with Mt5ArchBridge (or METAAPI_TOKEN). Password is present; this VM cannot binary-login MT5.`
        : `MT5 master or investor password for login ${mt5Login}, or METAAPI_TOKEN.`
    : "A personal WSF trading password or MetaAPI token.";

  const connectionStatus = deriveConnectionStatus({
    liveBalance: Boolean(liveBalance),
    usedOperator: useOperator,
    hasPassword: operator.hasMt5Password,
    winePrefixPresent,
    fileBridgePresent,
  });

  return {
    source: useOperator ? "operator-env" : WSF_HOME,
    fetchedAt: new Date().toISOString(),
    homepageOk,
    usedOfficialDemoCard,
    usedOperatorEnv: useOperator,
    email: email ? maskEmail(email) : null,
    identity: {
      email: email ? maskEmail(email) : null,
      nickname: ctrader.nickname,
      host: useOperator ? mt5Server : WSF_CTRADER_ID,
      login: snapshotLogin,
      server: snapshotServer,
      platform: "MT5",
      hasPassword: operator.hasMt5Password,
      credentialSource: useOperator ? "operator-env" : usedOfficialDemoCard ? "homepage-demo" : "none",
    },
    platforms: [mt5, ctrader.probe, matchTrader],
    books,
    openPositions,
    recentDeals,
    fetchNotes,
    bookHonesty,
    ordersPlaced: false,
    portal: WSF_PORTAL,
    nextSecretNeeded,
    winePrefixPresent,
    fileBridgePresent,
    connectionStatus,
    login: snapshotLogin,
    server: snapshotServer,
    balance: liveBalance?.balance ?? null,
    equity: liveBalance?.equity ?? null,
    currency: liveBalance?.currency ?? null,
  };
}

function deriveConnectionStatus(input: {
  liveBalance: boolean;
  usedOperator: boolean;
  hasPassword: boolean;
  winePrefixPresent: boolean;
  fileBridgePresent: boolean;
}): WsfConnectionStatus {
  if (input.liveBalance) return "connected";
  if (!input.usedOperator) return "no_credentials";
  if (!input.hasPassword) return "password_missing";
  if (!input.winePrefixPresent || !input.fileBridgePresent) return "missing_wine";
  return "auth_failed";
}

export function accountSnapshot(report: WsfLiveReport) {
  return {
    connectionStatus: report.connectionStatus,
    login: report.login,
    server: report.server,
    balance: report.balance,
    equity: report.equity,
    currency: report.currency,
    fetchedAt: report.fetchedAt,
    usedOperatorEnv: report.usedOperatorEnv,
    identity: report.identity,
    bookHonesty: report.bookHonesty,
    books: report.books,
    positions: report.openPositions,
    deals: report.recentDeals,
    openPositions: report.openPositions,
    recentDeals: report.recentDeals,
    fetchNotes: report.fetchNotes,
    ordersPlaced: report.ordersPlaced,
    nextSecretNeeded: report.nextSecretNeeded,
    winePrefixPresent: report.winePrefixPresent,
    fileBridgePresent: report.fileBridgePresent,
  };
}
