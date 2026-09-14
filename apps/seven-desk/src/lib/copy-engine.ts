import { paperAdapter } from "@/lib/adapters/paper";
import { uid } from "@/lib/ids";
import { floatingPnl, markForSide, quoteBySymbol } from "@/lib/quotes";
import type {
  BlotterEvent,
  CopySettings,
  DeskState,
  MasterTradeInput,
  Position,
  Side,
  TradingAccount,
} from "@/lib/types";
import { ALPHACAPITAL_LIVE_PENDING } from "@/lib/alphacapital/types";
import { FUNDEDNEXT_LIVE_PENDING, FUNDEDNEXT_LIVE_SYMBOLS } from "@/lib/fundednext/types";
import { FORTRADERS_LIVE_PENDING, FORTRADERS_LIVE_SYMBOLS } from "@/lib/fortraders/types";
import { FUNDINGPIPS_LIVE_PENDING, FUNDINGPIPS_LIVE_SYMBOLS } from "@/lib/fundingpips/types";
import { NEOMAA_LIVE_PENDING, NEOMAA_LIVE_SYMBOLS } from "@/lib/neomaa/types";
import { defaultLotsForFirm, liveLotsForFirm } from "@/lib/firms";
import { FTMO_LIVE_PENDING } from "@/lib/ftmo/types";
import { isAlreadyFlatReason, isPendingOrderType, isUs30Family } from "@/lib/live-order/guards";
import type { LiveBroker, LiveOrderResult, LiveOrderType } from "@/lib/live-order/types";
import { WSF_LIVE_PENDING, WSF_LIVE_SYMBOLS } from "@/lib/wsf/constants";
import type { BridgeOpenPosition, BridgePendingOrder } from "@/lib/bridge-orders";
import { armedCopyBrokers, COPY_FANOUT_SKIP, liveUs30SlError } from "@/lib/copy-fanout";
import { DESK_MAGIC } from "@/lib/desk-magic";

export const BLOTTER_LIMIT = 200;

export function resolveSymbol(
  masterSymbol: string,
  symbolMap: Record<string, string>
): { ok: true; symbol: string } | { ok: false; reason: "symbol unmapped" } {
  if (Object.prototype.hasOwnProperty.call(symbolMap, masterSymbol)) {
    const mapped = symbolMap[masterSymbol]?.trim() ?? "";
    if (!mapped) return { ok: false, reason: "symbol unmapped" };
    return { ok: true, symbol: mapped };
  }
  return { ok: true, symbol: masterSymbol };
}

export function sizeLots(
  masterLots: number,
  multiplier: number,
  maxLot: number
):
  | { ok: true; lots: number }
  | { ok: false; reason: "max lot" | "lot too small" } {
  const lots = Math.round(masterLots * multiplier * 100) / 100;
  if (lots < 0.01) return { ok: false, reason: "lot too small" };
  if (lots - maxLot > 1e-9) return { ok: false, reason: "max lot" };
  return { ok: true, lots };
}

export function applySide(side: Side, reverse: boolean): Side {
  if (!reverse) return side;
  return side === "buy" ? "sell" : "buy";
}

export function applySlTp(
  reverse: boolean,
  copySlTp: boolean,
  sl: number | null,
  tp: number | null
): { sl: number | null; tp: number | null } {
  if (!copySlTp) return { sl: null, tp: null };
  if (!reverse) return { sl, tp };
  return { sl: tp, tp: sl };
}

function settingsFor(
  copySettings: CopySettings[],
  accountId: string
): CopySettings | undefined {
  return copySettings.find((row) => row.slaveAccountId === accountId);
}

function pushBlotter(blotter: BlotterEvent[], event: BlotterEvent): BlotterEvent[] {
  return [event, ...blotter].slice(0, BLOTTER_LIMIT);
}

function refreshEquity(
  account: TradingAccount,
  positions: Position[]
): TradingAccount {
  const floating = positions
    .filter((position) => position.accountId === account.id)
    .reduce((sum, position) => sum + position.pnl, 0);
  return { ...account, equity: account.balance + floating };
}

export function applyQuoteMarks(state: DeskState): DeskState {
  const positions = state.positions.map((position) => {
    if (position.livePending) {
      return { ...position, pnl: 0, mark: position.entry };
    }
    const quote = quoteBySymbol(state.quotes, position.symbol);
    if (!quote) return position;
    const mark = markForSide(quote, position.side);
    return {
      ...position,
      mark,
      pnl: floatingPnl(position.side, position.lots, position.entry, mark, position.symbol),
    };
  });
  const accounts = state.accounts.map((account) => refreshEquity(account, positions));
  return { ...state, positions, accounts };
}

export function placeMasterTrade(
  state: DeskState,
  input: MasterTradeInput
): { state: DeskState; error?: string; groupId?: string } {
  const master = state.accounts.find((account) => account.id === state.masterId);
  if (!master) return { state, error: "No master account selected." };
  if (input.lots < 0.01) return { state, error: "Lots must be at least 0.01." };
  if (!input.symbol) return { state, error: "Choose a symbol." };

  const quote = paperAdapter.getQuote(input.symbol, state.quotes);
  if (!quote) return { state, error: `No paper quote for ${input.symbol}.` };

  const orderType: LiveOrderType = input.orderType ?? "market";
  const pending = isPendingOrderType(orderType);
  const requestedPrice =
    pending && input.price != null && input.price > 0
      ? input.price
      : input.side === "buy"
        ? quote.ask
        : quote.bid;
  if (pending && !(input.price != null && input.price > 0)) {
    return { state, error: "Pending limit/stop needs a price." };
  }

  const groupId = uid("grp");
  const now = Date.now();

  if (!pending) {
    const fill = paperAdapter.placeMarket(master, input, state.quotes);
    if (!fill.ok) {
      const event: BlotterEvent = {
        id: uid("blt"),
        groupId,
        accountId: master.id,
        role: "master",
        symbol: input.symbol,
        side: input.side,
        lots: input.lots,
        requestedPrice,
        orderType,
        sl: input.sl,
        tp: input.tp,
        status: "error",
        reason: fill.reason,
        createdAt: now,
        updatedAt: now,
      };
      return {
        state: { ...state, blotter: pushBlotter(state.blotter, event) },
        error: `Master rejected: ${fill.reason}`,
        groupId,
      };
    }

    const masterPosition: Position = {
      id: uid("pos"),
      accountId: master.id,
      symbol: input.symbol,
      side: input.side,
      lots: input.lots,
      entry: fill.fill.price,
      sl: input.sl,
      tp: input.tp,
      openedAt: fill.fill.at,
      mark: fill.fill.price,
      pnl: 0,
      orderType,
      groupId,
    };

    const masterEvent: BlotterEvent = {
      id: uid("blt"),
      groupId,
      accountId: master.id,
      role: "master",
      symbol: input.symbol,
      side: input.side,
      lots: input.lots,
      requestedPrice,
      fillPrice: fill.fill.price,
      orderType,
      sl: input.sl,
      tp: input.tp,
      status: "filled",
      reason: `paper fill · ${fill.fill.slippagePips.toFixed(2)} pip slip`,
      createdAt: now,
      updatedAt: now,
    };

    const slaveEvents: BlotterEvent[] = state.accounts
      .filter((account) => account.id !== master.id)
      .map((account) => ({
        id: uid("blt"),
        groupId,
        accountId: account.id,
        role: "slave" as const,
        symbol: input.symbol,
        side: input.side,
        lots: input.lots,
        requestedPrice,
        orderType,
        sl: input.sl,
        tp: input.tp,
        status: "queued" as const,
        reason: "waiting on copy engine",
        createdAt: now,
        updatedAt: now,
      }));

    const next: DeskState = {
      ...state,
      positions: [masterPosition, ...state.positions],
      blotter: [masterEvent, ...slaveEvents, ...state.blotter].slice(0, BLOTTER_LIMIT),
    };
    return { state: applyQuoteMarks(next), groupId };
  }

  const masterPosition: Position = {
    id: uid("pos"),
    accountId: master.id,
    symbol: input.symbol,
    side: input.side,
    lots: input.lots,
    entry: requestedPrice,
    sl: input.sl,
    tp: input.tp,
    openedAt: now,
    mark: requestedPrice,
    pnl: 0,
    livePending: true,
    orderType,
    groupId,
  };

  const masterEvent: BlotterEvent = {
    id: uid("blt"),
    groupId,
    accountId: master.id,
    role: "master",
    symbol: input.symbol,
    side: input.side,
    lots: input.lots,
    requestedPrice,
    fillPrice: requestedPrice,
    orderType,
    sl: input.sl,
    tp: input.tp,
    status: "filled",
    reason: `paper ${orderType}`,
    createdAt: now,
    updatedAt: now,
  };

  const slaveEvents: BlotterEvent[] = state.accounts
    .filter((account) => account.id !== master.id)
    .map((account) => ({
      id: uid("blt"),
      groupId,
      accountId: account.id,
      role: "slave" as const,
      symbol: input.symbol,
      side: input.side,
      lots: input.lots,
      requestedPrice,
      orderType,
      sl: input.sl,
      tp: input.tp,
      status: "queued" as const,
      reason: "waiting on copy engine",
      createdAt: now,
      updatedAt: now,
    }));

  const next: DeskState = {
    ...state,
    positions: [masterPosition, ...state.positions],
    blotter: [masterEvent, ...slaveEvents, ...state.blotter].slice(0, BLOTTER_LIMIT),
  };
  return { state: applyQuoteMarks(next), groupId };
}

export function resolveQueuedCopies(state: DeskState, groupId: string): DeskState {
  const masterEvent = state.blotter.find(
    (event) => event.groupId === groupId && event.role === "master"
  );
  if (!masterEvent || masterEvent.status !== "filled") return state;

  let blotter = state.blotter;
  let positions = state.positions;

  for (const event of state.blotter.filter(
    (row) => row.groupId === groupId && row.role === "slave" && row.status === "queued"
  )) {
    const account = state.accounts.find((row) => row.id === event.accountId);
    const resolved = resolveOneSlave(state, account, masterEvent, event);
    blotter = blotter.map((row) => (row.id === event.id ? resolved.event : row));
    if (resolved.position) positions = [resolved.position, ...positions];
  }

  return applyQuoteMarks({ ...state, blotter, positions });
}

function resolveOneSlave(
  state: DeskState,
  account: TradingAccount | undefined,
  master: BlotterEvent,
  queued: BlotterEvent
): { event: BlotterEvent; position?: Position } {
  const now = Date.now();
  const orderType: LiveOrderType = master.orderType ?? "market";
  const base: BlotterEvent = {
    ...queued,
    symbol: master.symbol,
    side: master.side,
    lots: master.lots,
    requestedPrice: master.requestedPrice,
    orderType,
    sl: master.sl,
    tp: master.tp,
    updatedAt: now,
  };

  if (!account) {
    return {
      event: {
        ...base,
        status: "error",
        reason: "account missing",
      },
    };
  }

  const patchedBase = { ...base, accountId: account.id };
  const settings = settingsFor(state.copySettings, account.id);

  if (!settings) {
    return {
      event: { ...patchedBase, status: "skipped", reason: "no copy settings" },
    };
  }
  if (!settings.enabled) {
    return {
      event: { ...patchedBase, status: "skipped", reason: "slave disabled" },
    };
  }
  if (account.status !== "connected") {
    return {
      event: {
        ...patchedBase,
        status: "error",
        reason:
          account.status === "error"
            ? account.statusReason ?? "account error"
            : "account disconnected",
      },
    };
  }

  const mapped = resolveSymbol(master.symbol, settings.symbolMap);
  if (!mapped.ok) {
    return {
      event: { ...patchedBase, status: "skipped", reason: mapped.reason },
    };
  }

  const side = applySide(master.side, settings.reverse);
  const levels = applySlTp(settings.reverse, settings.copySlTp, master.sl, master.tp);

  if (state.wsfLiveCopy && account.firmId === "wsf") {
    const liveSymbol = mapped.symbol === "EURUSD" ? "EURUSDc" : mapped.symbol;
    if (!WSF_LIVE_SYMBOLS.includes(liveSymbol as (typeof WSF_LIVE_SYMBOLS)[number])) {
      return {
        event: {
          ...patchedBase,
          symbol: liveSymbol,
          side,
          lots: liveLotsForFirm(account.firmId, master.lots),
          orderType,
          sl: levels.sl,
          tp: levels.tp,
          status: "skipped",
          reason: "symbol not on WSF live path (EURUSDc only)",
        },
      };
    }
    return {
      event: {
        ...patchedBase,
        symbol: liveSymbol,
        side,
        lots: liveLotsForFirm(account.firmId, master.lots),
        orderType,
        sl: levels.sl,
        tp: levels.tp,
        status: "queued",
        reason: WSF_LIVE_PENDING,
      },
    };
  }

  if (state.fundednextLiveCopy && account.firmId === "fundednext") {
    const liveSymbol = mapped.symbol === "EURUSDc" ? "EURUSD" : mapped.symbol;
    if (!FUNDEDNEXT_LIVE_SYMBOLS.includes(liveSymbol as (typeof FUNDEDNEXT_LIVE_SYMBOLS)[number])) {
      return {
        event: {
          ...patchedBase,
          symbol: liveSymbol,
          side,
          lots: liveLotsForFirm(account.firmId, master.lots),
          sl: levels.sl,
          tp: levels.tp,
          status: "skipped",
          reason: "symbol not on FundedNext live path (EURUSD only)",
        },
      };
    }
    return {
      event: {
        ...patchedBase,
        symbol: liveSymbol,
        side,
        lots: liveLotsForFirm(account.firmId, master.lots),
        sl: levels.sl,
        tp: levels.tp,
        status: "queued",
        reason: FUNDEDNEXT_LIVE_PENDING,
      },
    };
  }

  if (account.firmId === "alphacapital") {
    return {
      event: {
        ...patchedBase,
        symbol: mapped.symbol === "EURUSDc" ? "EURUSD" : mapped.symbol,
        side,
        lots: liveLotsForFirm(account.firmId, master.lots),
        sl: levels.sl,
        tp: levels.tp,
        status: "skipped",
        reason: "alpha capital is fetch-only — not copied",
      },
    };
  }

  if (state.fundingpipsLiveCopy && account.firmId === "fundingpips") {
    const liveSymbol = mapped.symbol === "EURUSDc" ? "EURUSD" : mapped.symbol;
    if (!FUNDINGPIPS_LIVE_SYMBOLS.includes(liveSymbol as (typeof FUNDINGPIPS_LIVE_SYMBOLS)[number])) {
      return {
        event: {
          ...patchedBase,
          symbol: liveSymbol,
          side,
          lots: liveLotsForFirm(account.firmId, master.lots),
          sl: levels.sl,
          tp: levels.tp,
          status: "skipped",
          reason: "symbol not on FundingPips live path (EURUSD only)",
        },
      };
    }
    return {
      event: {
        ...patchedBase,
        symbol: liveSymbol,
        side,
        lots: liveLotsForFirm(account.firmId, master.lots),
        sl: levels.sl,
        tp: levels.tp,
        status: "queued",
        reason: FUNDINGPIPS_LIVE_PENDING,
      },
    };
  }

  if (state.neomaaLiveCopy && account.firmId === "neomaa") {
    const liveSymbol = mapped.symbol === "EURUSDc" ? "EURUSD" : mapped.symbol;
    if (!NEOMAA_LIVE_SYMBOLS.includes(liveSymbol as (typeof NEOMAA_LIVE_SYMBOLS)[number])) {
      return {
        event: {
          ...patchedBase,
          symbol: liveSymbol,
          side,
          lots: liveLotsForFirm(account.firmId, master.lots),
          sl: levels.sl,
          tp: levels.tp,
          status: "skipped",
          reason: "symbol not on Neomaa live path (EURUSD only)",
        },
      };
    }
    return {
      event: {
        ...patchedBase,
        symbol: liveSymbol,
        side,
        lots: liveLotsForFirm(account.firmId, master.lots),
        sl: levels.sl,
        tp: levels.tp,
        status: "queued",
        reason: NEOMAA_LIVE_PENDING,
      },
    };
  }

  if (state.fortradersLiveCopy && account.firmId === "fortraders") {
    const liveSymbol = mapped.symbol === "EURUSDc" ? "EURUSD" : mapped.symbol;
    if (!FORTRADERS_LIVE_SYMBOLS.includes(liveSymbol as (typeof FORTRADERS_LIVE_SYMBOLS)[number])) {
      return {
        event: {
          ...patchedBase,
          symbol: liveSymbol,
          side,
          lots: liveLotsForFirm(account.firmId, master.lots),
          sl: levels.sl,
          tp: levels.tp,
          status: "skipped",
          reason: "symbol not on Fortraders live path (EURUSD only)",
        },
      };
    }
    return {
      event: {
        ...patchedBase,
        symbol: liveSymbol,
        side,
        lots: liveLotsForFirm(account.firmId, master.lots),
        sl: levels.sl,
        tp: levels.tp,
        status: "queued",
        reason: FORTRADERS_LIVE_PENDING,
      },
    };
  }

  const lots = liveLotsForFirm(account.firmId, master.lots);
  if (lots - settings.maxLot > 1e-9) {
    return {
      event: {
        ...patchedBase,
        symbol: mapped.symbol,
        side,
        sl: levels.sl,
        tp: levels.tp,
        status: "skipped",
        reason: "max lot",
      },
    };
  }

  if (isPendingOrderType(orderType)) {
    const pendingPrice = master.requestedPrice;
    const position: Position = {
      id: uid("pos"),
      accountId: account.id,
      symbol: mapped.symbol,
      side,
      lots: lots,
      entry: pendingPrice,
      sl: levels.sl,
      tp: levels.tp,
      openedAt: now,
      mark: pendingPrice,
      pnl: 0,
      livePending: true,
      orderType,
      groupId: master.groupId,
    };
    return {
      event: {
        ...patchedBase,
        symbol: mapped.symbol,
        side,
        lots: lots,
        orderType,
        sl: levels.sl,
        tp: levels.tp,
        fillPrice: pendingPrice,
        status: "filled",
        reason: `paper ${orderType}`,
      },
      position,
    };
  }

  const result = paperAdapter.placeMarket(
    account,
    {
      symbol: mapped.symbol,
      side,
      lots: lots,
      sl: levels.sl,
      tp: levels.tp,
    },
    state.quotes
  );

  if (!result.ok) {
    return {
      event: {
        ...patchedBase,
        symbol: mapped.symbol,
        side,
        lots: lots,
        sl: levels.sl,
        tp: levels.tp,
        status: "error",
        reason: result.reason,
      },
    };
  }

  if (result.fill.slippagePips - settings.maxSlippagePips > 1e-9) {
    return {
      event: {
        ...patchedBase,
        symbol: mapped.symbol,
        side,
        lots: lots,
        sl: levels.sl,
        tp: levels.tp,
        fillPrice: result.fill.price,
        status: "skipped",
        reason: "max slippage",
      },
    };
  }

  const position: Position = {
    id: uid("pos"),
    accountId: account.id,
    symbol: mapped.symbol,
    side,
    lots: lots,
    entry: result.fill.price,
    sl: levels.sl,
    tp: levels.tp,
    openedAt: result.fill.at,
    mark: result.fill.price,
    pnl: 0,
    groupId: master.groupId,
  };

  return {
    event: {
      ...patchedBase,
      symbol: mapped.symbol,
      side,
      lots: lots,
      sl: levels.sl,
      tp: levels.tp,
      fillPrice: result.fill.price,
      status: "filled",
      reason: settings.reverse
        ? `reversed · ${result.fill.slippagePips.toFixed(2)} pip slip`
        : `copied · ${result.fill.slippagePips.toFixed(2)} pip slip`,
    },
    position,
  };
}

export function closePosition(
  state: DeskState,
  positionId: string
): { state: DeskState; error?: string } {
  const position = state.positions.find((row) => row.id === positionId);
  if (!position) return { state, error: "Position already closed." };
  const account = state.accounts.find((row) => row.id === position.accountId);
  if (!account) return { state, error: "Account missing." };

  const result = paperAdapter.closeMarket(
    account,
    position.symbol,
    position.side,
    state.quotes
  );
  if (!result.ok) return { state, error: result.reason };

  const quote = quoteBySymbol(state.quotes, position.symbol);
  const mark = quote ? markForSide(quote, position.side) : result.fill.price;
  const pnl = floatingPnl(
    position.side,
    position.lots,
    position.entry,
    mark,
    position.symbol
  );

  const now = Date.now();
  const event: BlotterEvent = {
    id: uid("blt"),
    groupId: uid("cls"),
    accountId: account.id,
    role: account.id === state.masterId ? "master" : "slave",
    symbol: position.symbol,
    side: position.side,
    lots: position.lots,
    requestedPrice: mark,
    fillPrice: mark,
    sl: position.sl,
    tp: position.tp,
    status: "filled",
    reason: `closed · ${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}`,
    createdAt: now,
    updatedAt: now,
  };

  const accounts = state.accounts.map((row) =>
    row.id === account.id ? { ...row, balance: row.balance + pnl } : row
  );

  const next: DeskState = {
    ...state,
    accounts,
    positions: state.positions.filter((row) => row.id !== position.id),
    blotter: pushBlotter(state.blotter, event),
  };
  return { state: applyQuoteMarks(next) };
}

export function isBrokerLeftover(row: Position): boolean {
  if (row.leftover === true) return true;
  if (row.leftover === false) return false;
  return Boolean(row.fromSnapshot && !row.groupId);
}

export function liveGroupPositions(state: DeskState, positionId: string): Position[] {
  const target = state.positions.find((row) => row.id === positionId);
  if (!target) return [];
  if (!target.liveBroker) return [target];
  if (!target.groupId) return [target];
  return state.positions.filter(
    (row) => row.liveBroker && row.groupId === target.groupId
  );
}

/** One live row per copy-group, plus every paper row. */
export function flattenAllTargets(state: DeskState): {
  liveRepIds: string[];
  paperIds: string[];
} {
  const seen = new Set<string>();
  const liveRepIds: string[] = [];
  const paperIds: string[] = [];
  for (const row of state.positions) {
    if (isBrokerLeftover(row)) continue;
    if (row.liveBroker) {
      const key = row.groupId ?? row.id;
      if (seen.has(key)) continue;
      seen.add(key);
      liveRepIds.push(row.id);
    } else {
      paperIds.push(row.id);
    }
  }
  return { liveRepIds, paperIds };
}

/** Counts for the always-visible flatten bar. US30/DJ30 desk rows are included. */
export function describeFlattenTargets(state: DeskState): {
  filled: number;
  pending: number;
  leftovers: number;
  us30Rows: { symbol: string; lots: number; pending: boolean }[];
} {
  let filled = 0;
  let pending = 0;
  let leftovers = 0;
  const us30Rows: { symbol: string; lots: number; pending: boolean }[] = [];
  for (const row of state.positions) {
    if (isBrokerLeftover(row)) {
      leftovers += 1;
      continue;
    }
    if (row.livePending) pending += 1;
    else filled += 1;
    if (isUs30Family(row.symbol)) {
      us30Rows.push({
        symbol: row.symbol,
        lots: row.lots,
        pending: Boolean(row.livePending),
      });
    }
  }
  return { filled, pending, leftovers, us30Rows };
}

export function liveCloseAlreadyFlat(result: LiveOrderResult): boolean {
  if (result.ok) return true;
  return isAlreadyFlatReason(result.reason ?? "");
}

export function markLiveCloseError(
  state: DeskState,
  positionId: string,
  reason: string
): DeskState {
  const position = state.positions.find((row) => row.id === positionId);
  if (!position) return state;
  const now = Date.now();
  const event: BlotterEvent = {
    id: uid("blt"),
    groupId: position.groupId ?? uid("cls"),
    accountId: position.accountId,
    role: "slave",
    symbol: position.symbol,
    side: position.side,
    lots: position.lots,
    requestedPrice: position.mark,
    sl: position.sl,
    tp: position.tp,
    status: "error",
    reason: reason || "live close failed — desk row kept",
    createdAt: now,
    updatedAt: now,
  };
  return { ...state, blotter: pushBlotter(state.blotter, event) };
}

export function pendingWsfLiveEvents(state: DeskState, groupId: string): BlotterEvent[] {
  return pendingLiveSlaveEvents(state, groupId).filter((event) => event.reason === WSF_LIVE_PENDING);
}

export function pendingLiveSlaveEvents(state: DeskState, groupId: string): BlotterEvent[] {
  return state.blotter.filter(
    (event) =>
      event.groupId === groupId &&
      event.role === "slave" &&
      event.status === "queued" &&
      event.reason !== ALPHACAPITAL_LIVE_PENDING &&
      (event.reason === WSF_LIVE_PENDING ||
        event.reason === FUNDEDNEXT_LIVE_PENDING ||
        event.reason === FTMO_LIVE_PENDING ||
        event.reason === FUNDINGPIPS_LIVE_PENDING ||
        event.reason === NEOMAA_LIVE_PENDING ||
        event.reason === FORTRADERS_LIVE_PENDING)
  );
}

function liveFillLabel(broker: LiveBroker, result: LiveOrderResult): string {
  const pending =
    result.stage === "pending" || isPendingOrderType(result.orderType);
  const kind = pending ? `${result.orderType ?? "limit"}` : "fill";
  const lots = result.volume && result.volume > 0 ? result.volume : defaultLotsForFirm(broker);
  const ms = result.holdMs != null && result.holdMs >= 0 ? ` · ${Math.round(result.holdMs)}ms` : "";
  if (broker === "wsf") return `HTTP send · live WSF 149736 · ${lots} ${kind} · order ${result.order ?? "—"}${ms}`;
  if (broker === "ftmo") return `HTTP send · live FTMO 541163357 · ${lots} ${kind} · order ${result.order ?? "—"}${ms}`;
  if (broker === "alphacapital") return `HTTP send · live ACG 2765247 · ${lots} ${kind} · order ${result.order ?? "—"}${ms}`;
  if (broker === "fundingpips") return `HTTP send · live FundingPips 11669306 · ${lots} ${kind} · order ${result.order ?? "—"}${ms}`;
  if (broker === "neomaa") return `HTTP send · live Neomaa 7745107 · ${lots} ${kind} · order ${result.order ?? "—"}${ms}`;
  if (broker === "fortraders") return `HTTP send · live Fortraders 737150 · ${lots} ${kind} · order ${result.order ?? "—"}${ms}`;
  return `HTTP send · live FN 13981906 · ${lots} ${kind} · order ${result.order ?? "—"}${ms}`;
}

export function applyLiveFill(
  state: DeskState,
  eventId: string,
  result: LiveOrderResult,
  broker: LiveBroker
): DeskState {
  const event = state.blotter.find((row) => row.id === eventId);
  if (!event) return state;
  const now = Date.now();
  if (!result.ok) {
    return {
      ...state,
      blotter: state.blotter.map((row) =>
        row.id === eventId
          ? {
              ...row,
              status: "error",
              reason: result.reason || `${broker} live order failed`,
              updatedAt: now,
            }
          : row
      ),
    };
  }
  const lots = result.volume && result.volume > 0 ? result.volume : defaultLotsForFirm(broker);
  const pending =
    result.stage === "pending" || isPendingOrderType(result.orderType ?? event.orderType);
  const price = (result.price && result.price > 0 ? result.price : null) ?? result.openPrice ?? event.requestedPrice;
  const orderType = (result.orderType as LiveOrderType | undefined) ?? event.orderType ?? "market";
  const position: Position = {
    id: uid("pos"),
    accountId: event.accountId,
    symbol: result.symbol ?? event.symbol,
    side: event.side,
    lots,
    entry: price,
    sl: event.sl,
    tp: event.tp,
    openedAt: now,
    mark: price,
    pnl: 0,
    liveBroker: broker,
    liveOrder: result.order,
    livePending: pending,
    leftover: false,
    orderType,
    groupId: event.groupId,
  };
  const blotter = state.blotter.map((row) =>
    row.id === eventId
      ? {
          ...row,
          status: "filled" as const,
          fillPrice: price,
          lots,
          orderType,
          reason: liveFillLabel(broker, result),
          liveTicket: result.order ?? result.ticket,
          latencyMs: result.holdMs,
          httpAction: "send" as const,
          updatedAt: now,
        }
      : row
  );
  return applyQuoteMarks({
    ...state,
    positions: [position, ...state.positions],
    blotter,
  });
}

export function applyWsfLiveFill(
  state: DeskState,
  eventId: string,
  result: LiveOrderResult
): DeskState {
  return applyLiveFill(state, eventId, result, "wsf");
}

export function placeLiveMasterFill(
  state: DeskState,
  input: MasterTradeInput,
  result: LiveOrderResult,
  broker: LiveBroker
): { state: DeskState; error?: string; groupId?: string } {
  const master = state.accounts.find((account) => account.id === state.masterId);
  if (!master) return { state, error: "No master account selected." };
  const groupId = uid("grp");
  const now = Date.now();
  const lots =
    result.volume && result.volume > 0 ? result.volume : liveLotsForFirm(broker, input.lots);
  const pending =
    result.stage === "pending" || isPendingOrderType(result.orderType ?? input.orderType);
  const orderType: LiveOrderType =
    (result.orderType as LiveOrderType | undefined) ?? input.orderType ?? "market";
  const fillPrice =
    (result.price && result.price > 0 ? result.price : 0) ||
    (result.openPrice && result.openPrice > 0 ? result.openPrice : 0) ||
    (input.price && input.price > 0 ? input.price : 0);
  if (!result.ok || (fillPrice <= 0 && !result.order)) {
    const event: BlotterEvent = {
      id: uid("blt"),
      groupId,
      accountId: master.id,
      role: "master",
      symbol: input.symbol,
      side: input.side,
      lots,
      requestedPrice: fillPrice || 0,
      orderType,
      sl: input.sl,
      tp: input.tp,
      status: "error",
      reason: result.reason || "live master OrderSend failed — not copying",
      createdAt: now,
      updatedAt: now,
    };
    return {
      state: { ...state, blotter: pushBlotter(state.blotter, event) },
      error: `Master rejected: ${result.reason || "live OrderSend failed"}`,
      groupId,
    };
  }

  const masterPosition: Position = {
    id: uid("pos"),
    accountId: master.id,
    symbol: result.symbol ?? input.symbol,
    side: input.side,
    lots,
    entry: fillPrice,
    sl: input.sl,
    tp: input.tp,
    openedAt: now,
    mark: fillPrice,
    pnl: 0,
    liveBroker: broker,
    liveOrder: result.order,
    livePending: pending,
    leftover: false,
    orderType,
    groupId,
  };
  const masterEvent: BlotterEvent = {
    id: uid("blt"),
    groupId,
    accountId: master.id,
    role: "master",
    symbol: result.symbol ?? input.symbol,
    side: input.side,
    lots,
    requestedPrice: fillPrice,
    fillPrice,
    orderType,
    sl: input.sl,
    tp: input.tp,
    status: "filled",
    reason: liveFillLabel(broker, result),
    createdAt: now,
    updatedAt: now,
    liveTicket: result.order ?? result.ticket,
    latencyMs: result.holdMs,
    httpAction: "send",
  };
  const slaveEvents: BlotterEvent[] = state.accounts
    .filter((account) => account.id !== master.id)
    .map((account) => ({
      id: uid("blt"),
      groupId,
      accountId: account.id,
      role: "slave" as const,
      symbol: input.symbol,
      side: input.side,
      lots,
      requestedPrice: fillPrice,
      orderType,
      sl: input.sl,
      tp: input.tp,
      status: "queued" as const,
      reason: "waiting on copy engine",
      createdAt: now,
      updatedAt: now,
    }));
  const next: DeskState = {
    ...state,
    positions: [masterPosition, ...state.positions],
    blotter: [masterEvent, ...slaveEvents, ...state.blotter].slice(0, BLOTTER_LIMIT),
  };
  return { state: applyQuoteMarks(next), groupId };
}

export function recordHttpBlotter(
  state: DeskState,
  input: {
    accountId: string;
    role: BlotterEvent["role"];
    symbol: string;
    side: Side;
    lots: number;
    price: number;
    orderType?: LiveOrderType;
    status: BlotterEvent["status"];
    reason: string;
    liveTicket?: number;
    latencyMs?: number;
    httpAction: "send" | "cancel" | "close" | "modify";
    groupId?: string;
  }
): DeskState {
  const now = Date.now();
  const event: BlotterEvent = {
    id: uid("blt"),
    groupId: input.groupId ?? uid("http"),
    accountId: input.accountId,
    role: input.role,
    symbol: input.symbol,
    side: input.side,
    lots: input.lots,
    requestedPrice: input.price,
    fillPrice: input.httpAction === "send" ? input.price : undefined,
    orderType: input.orderType,
    sl: null,
    tp: null,
    status: input.status,
    reason: input.reason,
    createdAt: now,
    updatedAt: now,
    liveTicket: input.liveTicket,
    latencyMs: input.latencyMs,
    httpAction: input.httpAction,
  };
  return { ...state, blotter: pushBlotter(state.blotter, event) };
}

function asLiveOrderType(type: string): LiveOrderType {
  if (
    type === "buy_limit" ||
    type === "sell_limit" ||
    type === "buy_stop" ||
    type === "sell_stop"
  ) {
    return type;
  }
  return "market";
}

export function upsertSnapshotPendings(
  state: DeskState,
  accountId: string,
  broker: LiveBroker,
  orders: BridgePendingOrder[]
): DeskState {
  if (COPY_FANOUT_SKIP.has(broker) && broker === "alphacapital") {
    // Still show Alpha RO pendings on the book; do not treat them as copy legs.
  }
  const keep = state.positions.filter((row) => {
    if (row.accountId !== accountId) return true;
    if (!row.fromSnapshot) return true;
    if (!row.livePending) return true;
    if (row.leftover === false && row.groupId) return true;
    return false;
  });
  const existingTickets = new Set(
    keep
      .filter((row) => row.accountId === accountId && row.liveOrder)
      .map((row) => row.liveOrder)
  );
  const now = Date.now();
  const added: Position[] = [];
  for (const order of orders) {
    if (existingTickets.has(order.ticket)) continue;
    const orderType = asLiveOrderType(order.type);
    added.push({
      id: uid("pos"),
      accountId,
      symbol: order.symbol,
      side: order.side === "sell" ? "sell" : "buy",
      lots: order.volume ?? 0,
      entry: order.price ?? 0,
      sl: order.sl,
      tp: order.tp,
      openedAt: now,
      mark: order.price ?? 0,
      pnl: 0,
      liveBroker: broker,
      liveOrder: order.ticket,
      livePending: isPendingOrderType(orderType) || order.status === "pending",
      fromSnapshot: true,
      leftover: true,
      orderType,
    });
  }
  return applyQuoteMarks({ ...state, positions: [...added, ...keep] });
}

export function upsertSnapshotPositions(
  state: DeskState,
  accountId: string,
  broker: LiveBroker,
  positions: BridgeOpenPosition[]
): DeskState {
  const incomingTickets = new Set(positions.map((pos) => pos.ticket));
  const keep = state.positions.filter((row) => {
    if (row.accountId !== accountId) return true;
    if (row.livePending) return true;
    if (row.fromSnapshot && row.leftover) {
      return Boolean(row.liveOrder && incomingTickets.has(row.liveOrder));
    }
    return true;
  });
  const byTicket = new Map<number, Position>();
  for (const row of keep) {
    if (row.accountId === accountId && row.liveOrder) {
      byTicket.set(row.liveOrder, row);
    }
  }
  const now = Date.now();
  const added: Position[] = [];
  for (const pos of positions) {
    const existing = byTicket.get(pos.ticket);
    if (existing) continue;
    added.push({
      id: uid("pos"),
      accountId,
      symbol: pos.symbol,
      side: pos.side === "sell" ? "sell" : "buy",
      lots: pos.volume ?? 0,
      entry: pos.price ?? 0,
      sl: pos.sl != null && pos.sl > 0 ? pos.sl : null,
      tp: pos.tp != null && pos.tp > 0 ? pos.tp : null,
      openedAt: now,
      mark: pos.price ?? 0,
      pnl: pos.profit ?? 0,
      liveBroker: broker,
      liveOrder: pos.ticket,
      livePending: false,
      fromSnapshot: true,
      leftover: true,
      magic: pos.magic,
      orderType: "market",
    });
  }
  const merged = keep.map((row) => {
    if (row.accountId !== accountId || !row.liveOrder || row.livePending) return row;
    const live = positions.find((pos) => pos.ticket === row.liveOrder);
    if (!live) return row;
    return {
      ...row,
      symbol: live.symbol || row.symbol,
      side: live.side === "sell" ? "sell" : live.side === "buy" ? "buy" : row.side,
      lots: live.volume ?? row.lots,
      entry: live.price ?? row.entry,
      sl: live.sl != null && live.sl > 0 ? live.sl : live.sl === 0 ? null : row.sl,
      tp: live.tp != null && live.tp > 0 ? live.tp : live.tp === 0 ? null : row.tp,
      mark: live.price ?? row.mark,
      pnl: live.profit ?? row.pnl,
      magic: live.magic ?? row.magic,
      leftover: row.leftover === false ? false : isBrokerLeftover(row),
    };
  });
  return applyQuoteMarks({ ...state, positions: [...added, ...merged] });
}

export function applyLiveModify(
  state: DeskState,
  positionId: string,
  sl: number | null,
  tp: number | null
): DeskState {
  const position = state.positions.find((row) => row.id === positionId);
  if (!position) return state;
  const now = Date.now();
  const nextSl = sl != null && sl > 0 ? sl : null;
  const nextTp = tp != null && tp > 0 ? tp : null;
  return {
    ...state,
    positions: state.positions.map((row) =>
      row.id === positionId ? { ...row, sl: nextSl, tp: nextTp } : row
    ),
    blotter: pushBlotter(state.blotter, {
      id: uid("blt"),
      groupId: uid("mod"),
      accountId: position.accountId,
      role: "slave",
      symbol: position.symbol,
      side: position.side,
      lots: position.lots,
      requestedPrice: position.entry,
      sl: nextSl,
      tp: nextTp,
      status: "filled",
      reason: `HTTP modify · SL ${nextSl ?? "—"} · TP ${nextTp ?? "—"}`,
      createdAt: now,
      updatedAt: now,
      httpAction: "modify",
    }),
  };
}

export function defaultCopySettings(slaveAccountId: string): CopySettings {
  return {
    slaveAccountId,
    enabled: true,
    lotMultiplier: 1,
    maxLot: defaultLotsForFirm("ftmo"),
    maxSlippagePips: 2,
    copySlTp: true,
    reverse: false,
    symbolMap: {},
  };
}

/** Session-only FTMO terminal follow. Not persisted. */
export interface FollowSession {
  baselineTickets: Set<number>;
  followGroups: Map<number, string>;
  pendingToGroup: Map<number, string>;
}

export type FollowDiffAction =
  | {
      kind: "open";
      ticket: number;
      source: "position" | "pending";
      symbol: string;
      side: Side;
      lots: number;
      sl: number | null;
      tp: number | null;
      orderType: LiveOrderType;
      livePending: boolean;
    }
  | {
      kind: "fill";
      pendingTicket: number;
      positionTicket: number;
      groupId: string;
    }
  | {
      kind: "close";
      ticket: number;
      groupId: string;
    }
  | {
      kind: "cancel";
      ticket: number;
      groupId: string;
    }
  | {
      kind: "modify";
      ticket: number;
      groupId: string;
      sl: number | null;
      tp: number | null;
    };

export interface FollowDiffResult {
  actions: FollowDiffAction[];
  next: FollowSession;
}

export function snapshotFollowBaseline(
  positions: BridgeOpenPosition[],
  pendings: BridgePendingOrder[]
): Set<number> {
  const tickets = new Set<number>();
  for (const row of positions) {
    if (row.ticket > 0) tickets.add(row.ticket);
  }
  for (const row of pendings) {
    if (row.ticket > 0) tickets.add(row.ticket);
  }
  return tickets;
}

export function createFollowSession(
  baselineTickets: Iterable<number> = [],
  followGroups?: Iterable<readonly [number, string]>,
  pendingToGroup?: Iterable<readonly [number, string]>
): FollowSession {
  return {
    baselineTickets: new Set(baselineTickets),
    followGroups: new Map(followGroups),
    pendingToGroup: new Map(pendingToGroup),
  };
}

function cloneFollowSession(session: FollowSession): FollowSession {
  return {
    baselineTickets: new Set(session.baselineTickets),
    followGroups: new Map(session.followGroups),
    pendingToGroup: new Map(session.pendingToGroup),
  };
}

function followLevel(value: number | null | undefined): number | null {
  if (value == null || !Number.isFinite(value) || value === 0) return null;
  return value;
}

function followLevelsChanged(a: number | null | undefined, b: number | null | undefined): boolean {
  return followLevel(a) !== followLevel(b);
}

function followLotsClose(a: number | null | undefined, b: number | null | undefined): boolean {
  return Math.abs((a ?? 0) - (b ?? 0)) <= 0.001;
}

function followSide(value: string | null | undefined): Side {
  return value === "sell" ? "sell" : "buy";
}

function followTrim(symbol: string | null | undefined): string {
  return (symbol ?? "").trim();
}

function isFtmoDeskOrigin(
  ticket: number,
  magic: number | null | undefined,
  deskPositions: Position[]
): boolean {
  if (magic === DESK_MAGIC.ftmo) return true;
  return deskPositions.some(
    (row) =>
      row.liveBroker === "ftmo" &&
      row.liveOrder === ticket &&
      row.leftover === false &&
      Boolean(row.groupId)
  );
}

function pendingMatchesPosition(
  pending: { symbol: string; side: Side; lots: number },
  position: BridgeOpenPosition
): boolean {
  if (followTrim(pending.symbol) !== followTrim(position.symbol)) return false;
  if (pending.side !== followSide(position.side)) return false;
  return followLotsClose(pending.lots, position.volume);
}

/** Pure FTMO follow diff. Baseline leftovers and desk-magic tickets never open. */
export function diffFollowTickets(
  session: FollowSession,
  positions: BridgeOpenPosition[],
  pendings: BridgePendingOrder[],
  deskPositions: Position[]
): FollowDiffResult {
  const next = cloneFollowSession(session);
  const actions: FollowDiffAction[] = [];
  const currentPos = new Set(positions.map((row) => row.ticket));
  const currentPend = new Set(pendings.map((row) => row.ticket));

  for (const [pendTicket, groupId] of session.pendingToGroup) {
    if (currentPend.has(pendTicket)) continue;
    const desk = deskPositions.find(
      (row) => row.liveBroker === "ftmo" && row.liveOrder === pendTicket
    );
    const pendingShape = desk
      ? { symbol: desk.symbol, side: desk.side, lots: desk.lots }
      : null;
    const candidates = pendingShape
      ? positions.filter(
          (row) =>
            !next.baselineTickets.has(row.ticket) &&
            !next.followGroups.has(row.ticket) &&
            !isFtmoDeskOrigin(row.ticket, row.magic, deskPositions) &&
            pendingMatchesPosition(pendingShape, row)
        )
      : [];
    const match = candidates.find((row) => !next.followGroups.has(row.ticket)) ?? null;
    if (match) {
      actions.push({
        kind: "fill",
        pendingTicket: pendTicket,
        positionTicket: match.ticket,
        groupId,
      });
      next.followGroups.delete(pendTicket);
      next.followGroups.set(match.ticket, groupId);
      next.pendingToGroup.delete(pendTicket);
      continue;
    }
    actions.push({ kind: "cancel", ticket: pendTicket, groupId });
    next.followGroups.delete(pendTicket);
    next.pendingToGroup.delete(pendTicket);
  }

  for (const pending of pendings) {
    if (next.baselineTickets.has(pending.ticket)) continue;
    const existingGroup =
      next.pendingToGroup.get(pending.ticket) ?? next.followGroups.get(pending.ticket);
    if (existingGroup) {
      const desk = deskPositions.find(
        (row) => row.liveBroker === "ftmo" && row.liveOrder === pending.ticket
      );
      if (
        desk &&
        (followLevelsChanged(desk.sl, pending.sl) || followLevelsChanged(desk.tp, pending.tp))
      ) {
        actions.push({
          kind: "modify",
          ticket: pending.ticket,
          groupId: existingGroup,
          sl: followLevel(pending.sl),
          tp: followLevel(pending.tp),
        });
      }
      continue;
    }
    if (isFtmoDeskOrigin(pending.ticket, null, deskPositions)) continue;
    const groupId = uid("grp");
    next.followGroups.set(pending.ticket, groupId);
    next.pendingToGroup.set(pending.ticket, groupId);
    actions.push({
      kind: "open",
      ticket: pending.ticket,
      source: "pending",
      symbol: pending.symbol,
      side: followSide(pending.side),
      lots: pending.volume ?? 0,
      sl: followLevel(pending.sl),
      tp: followLevel(pending.tp),
      orderType: asLiveOrderType(pending.type),
      livePending: true,
    });
  }

  for (const position of positions) {
    if (next.baselineTickets.has(position.ticket)) continue;
    const existingGroup = next.followGroups.get(position.ticket);
    if (existingGroup) {
      const desk = deskPositions.find(
        (row) => row.liveBroker === "ftmo" && row.liveOrder === position.ticket
      );
      if (
        desk &&
        (followLevelsChanged(desk.sl, position.sl) || followLevelsChanged(desk.tp, position.tp))
      ) {
        actions.push({
          kind: "modify",
          ticket: position.ticket,
          groupId: existingGroup,
          sl: followLevel(position.sl),
          tp: followLevel(position.tp),
        });
      }
      continue;
    }
    if (isFtmoDeskOrigin(position.ticket, position.magic, deskPositions)) continue;
    const groupId = uid("grp");
    next.followGroups.set(position.ticket, groupId);
    actions.push({
      kind: "open",
      ticket: position.ticket,
      source: "position",
      symbol: position.symbol,
      side: followSide(position.side),
      lots: position.volume ?? 0,
      sl: followLevel(position.sl),
      tp: followLevel(position.tp),
      orderType: "market",
      livePending: false,
    });
  }

  for (const [ticket, groupId] of session.followGroups) {
    if (session.pendingToGroup.has(ticket)) continue;
    if (currentPos.has(ticket)) continue;
    if (currentPend.has(ticket)) continue;
    if (!next.followGroups.has(ticket)) continue;
    actions.push({ kind: "close", ticket, groupId });
    next.followGroups.delete(ticket);
  }

  return { actions, next };
}

function dropFtmoTicket(state: DeskState, ticket: number): Position[] {
  return state.positions.filter(
    (row) =>
      !(
        row.liveBroker === "ftmo" &&
        row.liveOrder === ticket &&
        (row.leftover !== false || !row.groupId)
      )
  );
}

export function placeFollowMasterFill(
  state: DeskState,
  input: {
    ticket: number;
    symbol: string;
    side: Side;
    lots: number;
    sl: number | null;
    tp: number | null;
    orderType: LiveOrderType;
    livePending: boolean;
    groupId: string;
    price?: number | null;
    skipSlaves?: boolean;
  }
): DeskState {
  const master = state.accounts.find((account) => account.firmId === "ftmo");
  if (!master) return state;
  const now = Date.now();
  const fillPrice = input.price != null && input.price > 0 ? input.price : 0;
  const positions = dropFtmoTicket(state, input.ticket);
  const masterPosition: Position = {
    id: uid("pos"),
    accountId: master.id,
    symbol: input.symbol,
    side: input.side,
    lots: input.lots,
    entry: fillPrice,
    sl: input.sl,
    tp: input.tp,
    openedAt: now,
    mark: fillPrice,
    pnl: 0,
    liveBroker: "ftmo",
    liveOrder: input.ticket,
    livePending: input.livePending,
    leftover: false,
    fromSnapshot: true,
    followOrigin: true,
    orderType: input.orderType,
    groupId: input.groupId,
  };
  const masterEvent: BlotterEvent = {
    id: uid("blt"),
    groupId: input.groupId,
    accountId: master.id,
    role: "master",
    symbol: input.symbol,
    side: input.side,
    lots: input.lots,
    requestedPrice: fillPrice,
    fillPrice,
    orderType: input.orderType,
    sl: input.sl,
    tp: input.tp,
    status: "filled",
    reason: `follow · FTMO ticket ${input.ticket}`,
    createdAt: now,
    updatedAt: now,
    liveTicket: input.ticket,
    httpAction: "send",
  };
  const nakedUs30 = liveUs30SlError(input.symbol, input.sl, true);
  const skipSlaves = Boolean(input.skipSlaves) || Boolean(nakedUs30);
  const armed = skipSlaves ? [] : armedCopyBrokers(state);
  const slaveEvents: BlotterEvent[] = skipSlaves
    ? []
    : state.accounts
        .filter((account) => account.id !== master.id && armed.includes(account.firmId as LiveBroker))
        .map((account) => ({
          id: uid("blt"),
          groupId: input.groupId,
          accountId: account.id,
          role: "slave" as const,
          symbol: input.symbol,
          side: input.side,
          lots: input.lots,
          requestedPrice: fillPrice,
          orderType: input.orderType,
          sl: input.sl,
          tp: input.tp,
          status: "queued" as const,
          reason: "waiting on copy engine",
          createdAt: now,
          updatedAt: now,
        }));
  const blotterEvents = nakedUs30
    ? [
        masterEvent,
        {
          ...masterEvent,
          id: uid("blt"),
          status: "error" as const,
          reason: `follow · FTMO ticket ${input.ticket} · ${nakedUs30}`,
        },
      ]
    : [masterEvent, ...slaveEvents];
  return applyQuoteMarks({
    ...state,
    positions: [masterPosition, ...positions],
    blotter: [...blotterEvents, ...state.blotter].slice(0, BLOTTER_LIMIT),
  });
}

export function applyFollowFill(
  state: DeskState,
  input: {
    pendingTicket: number;
    positionTicket: number;
    groupId: string;
    position?: BridgeOpenPosition;
  }
): DeskState {
  const now = Date.now();
  let found = false;
  const nextPositions: Position[] = [];
  for (const row of state.positions) {
    if (
      row.liveBroker === "ftmo" &&
      row.liveOrder === input.positionTicket &&
      (row.leftover !== false || row.groupId !== input.groupId)
    ) {
      continue;
    }
    if (
      row.groupId === input.groupId &&
      row.liveBroker === "ftmo" &&
      (row.liveOrder === input.pendingTicket || row.livePending)
    ) {
      found = true;
      nextPositions.push({
        ...row,
        liveOrder: input.positionTicket,
        livePending: false,
        leftover: false,
        fromSnapshot: true,
        followOrigin: true,
        orderType: "market",
        entry: input.position?.price ?? row.entry,
        sl: input.position ? followLevel(input.position.sl) : row.sl,
        tp: input.position ? followLevel(input.position.tp) : row.tp,
        mark: input.position?.price ?? row.mark,
        pnl: input.position?.profit ?? row.pnl,
      });
      continue;
    }
    nextPositions.push(row);
  }
  if (!found && input.position) {
    const master = state.accounts.find((account) => account.firmId === "ftmo");
    if (master) {
      nextPositions.unshift({
        id: uid("pos"),
        accountId: master.id,
        symbol: input.position.symbol,
        side: followSide(input.position.side),
        lots: input.position.volume ?? 0,
        entry: input.position.price ?? 0,
        sl: followLevel(input.position.sl),
        tp: followLevel(input.position.tp),
        openedAt: now,
        mark: input.position.price ?? 0,
        pnl: input.position.profit ?? 0,
        liveBroker: "ftmo",
        liveOrder: input.positionTicket,
        livePending: false,
        leftover: false,
        fromSnapshot: true,
        followOrigin: true,
        orderType: "market",
        groupId: input.groupId,
      });
    }
  }
  const event: BlotterEvent = {
    id: uid("blt"),
    groupId: input.groupId,
    accountId: state.accounts.find((account) => account.firmId === "ftmo")?.id ?? state.masterId,
    role: "master",
    symbol: input.position?.symbol ?? "EURUSD",
    side: followSide(input.position?.side),
    lots: input.position?.volume ?? 0,
    requestedPrice: input.position?.price ?? 0,
    fillPrice: input.position?.price ?? 0,
    orderType: "market",
    sl: followLevel(input.position?.sl),
    tp: followLevel(input.position?.tp),
    status: "filled",
    reason: `follow · FTMO ticket ${input.positionTicket}`,
    createdAt: now,
    updatedAt: now,
    liveTicket: input.positionTicket,
    httpAction: "send",
  };
  return applyQuoteMarks({
    ...state,
    positions: nextPositions,
    blotter: pushBlotter(state.blotter, event),
  });
}

export function applyFollowMasterLevels(
  state: DeskState,
  groupId: string,
  sl: number | null,
  tp: number | null
): DeskState {
  return {
    ...state,
    positions: state.positions.map((row) =>
      row.groupId === groupId && row.liveBroker === "ftmo" ? { ...row, sl, tp } : row
    ),
  };
}

export function dropDeskPosition(
  state: DeskState,
  positionId: string,
  reason: string,
  httpAction: "close" | "cancel" = "close"
): DeskState {
  const position = state.positions.find((row) => row.id === positionId);
  if (!position) return state;
  const now = Date.now();
  const event: BlotterEvent = {
    id: uid("blt"),
    groupId: position.groupId ?? uid("cls"),
    accountId: position.accountId,
    role: position.accountId === state.masterId ? "master" : "slave",
    symbol: position.symbol,
    side: position.side,
    lots: position.lots,
    requestedPrice: position.mark,
    sl: position.sl,
    tp: position.tp,
    status: "filled",
    reason,
    createdAt: now,
    updatedAt: now,
    liveTicket: position.liveOrder,
    httpAction,
  };
  return {
    ...state,
    positions: state.positions.filter((row) => row.id !== position.id),
    blotter: pushBlotter(state.blotter, event),
  };
}
