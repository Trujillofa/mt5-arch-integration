import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import {
  parseOpenPositions,
  parsePendingOrders,
  type BridgeOpenPosition,
  type BridgePendingOrder,
} from "@/lib/bridge-orders";
import { canReportConnected, type BridgeFreshness } from "@/lib/bridge-freshness";

function isFile(path: string): boolean {
  try {
    return existsSync(path) && statSync(path).isFile();
  } catch {
    return false;
  }
}

/** File-only. Empty when heartbeat is stale — leftover orders.json is not live. */
export function readPendingOrdersFromDirs(
  dirs: string[],
  freshness?: BridgeFreshness
): BridgePendingOrder[] {
  if (freshness && !canReportConnected(freshness)) return [];
  for (const dir of dirs) {
    const path = join(dir, "orders.json");
    if (!isFile(path)) continue;
    try {
      const parsed = parsePendingOrders(JSON.parse(readFileSync(path, "utf8")));
      return parsed;
    } catch {
      continue;
    }
  }
  return [];
}

/** File-only. Empty when heartbeat is stale — leftover positions.json is not live. */
export function readOpenPositionsFromDirs(
  dirs: string[],
  freshness?: BridgeFreshness
): BridgeOpenPosition[] {
  if (freshness && !canReportConnected(freshness)) return [];
  for (const dir of dirs) {
    const path = join(dir, "positions.json");
    if (!isFile(path)) continue;
    try {
      return parseOpenPositions(JSON.parse(readFileSync(path, "utf8")));
    } catch {
      continue;
    }
  }
  return [];
}
