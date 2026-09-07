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
import { isAlreadyFlatReason, isPendingOrderType } from "@/lib/live-order/guards";
import type { LiveBroker, LiveOrderResult, LiveOrderType } from "@/lib/live-order/types";
import { WSF_LIVE_PENDING, WSF_LIVE_SYMBOLS } from "@/lib/wsf/constants";
import type { BridgePendingOrder } from "@/lib/bridge-orders";
import { COPY_FANOUT_SKIP } from "@/lib/copy-fanout";

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

  const sized = sizeLots(master.lots, settings.lotMultiplier, settings.maxLot);
  if (!sized.ok) {
    return {
      event: {
        ...patchedBase,
        symbol: mapped.symbol,
        side,
        sl: levels.sl,
        tp: levels.tp,
        status: "skipped",
        reason: sized.reason,
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
      lots: sized.lots,
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
        lots: sized.lots,
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
      lots: sized.lots,
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
        lots: sized.lots,
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
        lots: sized.lots,
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
    lots: sized.lots,
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
      lots: sized.lots,
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
    httpAction: "send" | "cancel" | "close";
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
      orderType,
    });
  }
  return applyQuoteMarks({ ...state, positions: [...added, ...keep] });
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
