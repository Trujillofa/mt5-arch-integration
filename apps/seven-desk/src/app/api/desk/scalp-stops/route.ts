import { join } from "node:path";
import { alphacapitalBridgeCandidates, readAlphaCapitalEnv } from "@/lib/alphacapital/env";
import { fortradersBridgeCandidates, readFortradersEnv } from "@/lib/fortraders/env";
import { fundednextBridgeCandidates, readFundedNextEnv } from "@/lib/fundednext/env";
import { fundingpipsBridgeCandidates, readFundingPipsEnv } from "@/lib/fundingpips/env";
import { ftmoBridgeCandidates, readFtmoEnv } from "@/lib/ftmo/env";
import { neomaaBridgeCandidates, readNeomaaEnv } from "@/lib/neomaa/env";
import { resolveBridgeAtr } from "@/lib/live-order/bridge-atr";
import { suggestScalpStops } from "@/lib/live-order/atr-stops";
import { WSF_ONLY_PREFIX, wsfBrandTerminalDir, readOperatorEnv } from "@/lib/wsf/env";

export const dynamic = "force-dynamic";

const FORBIDDEN = new Set(["vantage", "fpmarkets"]);

function dirsForBroker(broker: string): string[] | null {
  if (FORBIDDEN.has(broker)) return null;
  if (broker === "ftmo") {
    const env = readFtmoEnv();
    return env.bridgeDir ? [env.bridgeDir, ...ftmoBridgeCandidates(env.winePrefix)] : ftmoBridgeCandidates(env.winePrefix);
  }
  if (broker === "fundednext") {
    const env = readFundedNextEnv();
    return env.bridgeDir
      ? [env.bridgeDir, ...fundednextBridgeCandidates(env.winePrefix)]
      : fundednextBridgeCandidates(env.winePrefix);
  }
  if (broker === "fundingpips") {
    const env = readFundingPipsEnv();
    return env.bridgeDir
      ? [env.bridgeDir, ...fundingpipsBridgeCandidates(env.winePrefix)]
      : fundingpipsBridgeCandidates(env.winePrefix);
  }
  if (broker === "neomaa") {
    const env = readNeomaaEnv();
    return env.bridgeDir
      ? [env.bridgeDir, ...neomaaBridgeCandidates(env.winePrefix)]
      : neomaaBridgeCandidates(env.winePrefix);
  }
  if (broker === "fortraders") {
    const env = readFortradersEnv();
    return env.bridgeDir
      ? [env.bridgeDir, ...fortradersBridgeCandidates(env.winePrefix)]
      : fortradersBridgeCandidates(env.winePrefix);
  }
  if (broker === "alphacapital") {
    const env = readAlphaCapitalEnv();
    return env.bridgeDir
      ? [env.bridgeDir, ...alphacapitalBridgeCandidates(env.winePrefix)]
      : alphacapitalBridgeCandidates(env.winePrefix);
  }
  if (broker === "wsf") {
    const env = readOperatorEnv();
    const branded = join(wsfBrandTerminalDir(), "MQL5", "Files", "mt5_arch");
    const dirs = [branded, join(WSF_ONLY_PREFIX, "drive_c", "Program Files", "WSFmarkets MT5 Terminal", "MQL5", "Files", "mt5_arch")];
    if (env.bridgeDir) dirs.unshift(env.bridgeDir);
    return dirs;
  }
  return null;
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const broker = (url.searchParams.get("broker") || "").trim().toLowerCase();
  const symbol = (url.searchParams.get("symbol") || "US30").trim();
  if (!broker) {
    return Response.json({ ok: false, reason: "broker required" }, { status: 400 });
  }
  if (FORBIDDEN.has(broker)) {
    return Response.json({ ok: false, reason: "Seven Desk does not read Vantage or FP" }, { status: 400 });
  }
  const dirs = dirsForBroker(broker);
  if (!dirs) {
    return Response.json({ ok: false, reason: "unknown broker" }, { status: 400 });
  }
  const resolved = resolveBridgeAtr({ broker, symbol, dirs });
  const side = (url.searchParams.get("side") || "buy").toLowerCase() === "sell" ? "sell" : "buy";
  const entry = Number(url.searchParams.get("entry"));
  const lots = Number(url.searchParams.get("lots"));
  const suggestion =
    Number.isFinite(entry) && entry > 0
      ? suggestScalpStops({
          side,
          entry,
          atr: resolved.atr,
          point: 1,
          lots: Number.isFinite(lots) && lots > 0 ? lots : undefined,
          contractSize: 1,
        })
      : null;
  return Response.json({
    ok: true,
    broker,
    symbol,
    atr: resolved.atr,
    source: resolved.source,
    heartbeatFresh: resolved.heartbeatFresh,
    suggestion,
  });
}
