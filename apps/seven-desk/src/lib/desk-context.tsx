"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import {
  applyQuoteMarks,
  flattenAllTargets,
  liveCloseAlreadyFlat,
  liveGroupPositions,
  pendingLiveSlaveEvents,
} from "@/lib/copy-engine";
import {
  applyLiveCopyResult,
  flattenPosition,
  getDeskSnapshot,
  getPersistError,
  getServerDeskSnapshot,
  markLiveCloseFailed,
  placeLiveMaster,
  placeTrade as placeTradeStore,
  resetDemo as resetDemoStore,
  resolveGroup,
  selectAccount as selectAccountStore,
  setConnection as setConnectionStore,
  setAlphacapitalLiveCopy as setAlphacapitalLiveCopyStore,
  setFundednextLiveCopy as setFundednextLiveCopyStore,
  setFortradersLiveCopy as setFortradersLiveCopyStore,
  setFundingpipsLiveCopy as setFundingpipsLiveCopyStore,
  setNeomaaLiveCopy as setNeomaaLiveCopyStore,
  setFtmoLiveMaster as setFtmoLiveMasterStore,
  setMaster as setMasterStore,
  setSymbolMap as setSymbolMapStore,
  setWsfLiveCopy as setWsfLiveCopyStore,
  subscribeDesk,
  updateAccount as updateAccountStore,
  updateCopy as updateCopyStore,
  patchDesk,
} from "@/lib/desk-store";
import { ALPHACAPITAL_LIVE_CONFIRM, ALPHACAPITAL_LIVE_PENDING } from "@/lib/alphacapital/types";
import { FUNDEDNEXT_LIVE_CONFIRM, FUNDEDNEXT_LIVE_PENDING } from "@/lib/fundednext/types";
import { FORTRADERS_LIVE_CONFIRM, FORTRADERS_LIVE_PENDING } from "@/lib/fortraders/types";
import { FUNDINGPIPS_LIVE_CONFIRM, FUNDINGPIPS_LIVE_PENDING } from "@/lib/fundingpips/types";
import { NEOMAA_LIVE_CONFIRM, NEOMAA_LIVE_PENDING } from "@/lib/neomaa/types";
import { FTMO_LIVE_CONFIRM } from "@/lib/ftmo/types";
import { LIVE_ORDER_CLIENT_BUDGET_MS } from "@/lib/live-order/guards";
import type { LiveBroker, LiveOrderResult } from "@/lib/live-order/types";
import { WSF_LIVE_CONFIRM, WSF_LIVE_PENDING } from "@/lib/wsf/constants";
import { nudgeQuotes } from "@/lib/quotes";
import type {
  ConnectionStatus,
  CopySettings,
  DeskState,
  MasterTradeInput,
  TradingAccount,
} from "@/lib/types";

type Hydration = "loading" | "ready" | "error";

interface DeskApi {
  hydration: Hydration;
  hydrateError: string | null;
  state: DeskState;
  busy: boolean;
  selectAccount: (id: string) => void;
  setMaster: (id: string) => void;
  updateAccount: (id: string, patch: Partial<TradingAccount>) => void;
  setConnection: (id: string, status: ConnectionStatus, reason?: string) => void;
  updateCopy: (slaveAccountId: string, patch: Partial<CopySettings>) => void;
  setSymbolMap: (slaveAccountId: string, masterSymbol: string, mapped: string) => void;
  placeTrade: (input: MasterTradeInput) => string | null;
  flatten: (positionId: string) => string | null;
  flattenAll: () => string | null;
  actionError: string | null;
  resetDemo: () => void;
  setWsfLiveCopy: (enabled: boolean, confirm: string) => string | null;
  setFtmoLiveMaster: (enabled: boolean, confirm: string) => string | null;
  setFundednextLiveCopy: (enabled: boolean, confirm: string) => string | null;
  setAlphacapitalLiveCopy: (enabled: boolean, confirm: string) => string | null;
  setFundingpipsLiveCopy: (enabled: boolean, confirm: string) => string | null;
  setNeomaaLiveCopy: (enabled: boolean, confirm: string) => string | null;
  setFortradersLiveCopy: (enabled: boolean, confirm: string) => string | null;
}

const DeskContext = createContext<DeskApi | null>(null);

function endpointFor(broker: LiveBroker, action: "open" | "close"): string {
  if (broker === "wsf") return action === "close" ? "/api/wsf/order/close" : "/api/wsf/order";
  if (broker === "ftmo") return action === "close" ? "/api/ftmo/order/close" : "/api/ftmo/order";
  if (broker === "alphacapital") {
    return action === "close" ? "/api/alphacapital/order/close" : "/api/alphacapital/order";
  }
  if (broker === "fundingpips") {
    return action === "close" ? "/api/fundingpips/order/close" : "/api/fundingpips/order";
  }
  if (broker === "neomaa") {
    return action === "close" ? "/api/neomaa/order/close" : "/api/neomaa/order";
  }
  if (broker === "fortraders") {
    return action === "close" ? "/api/fortraders/order/close" : "/api/fortraders/order";
  }
  return action === "close" ? "/api/fundednext/order/close" : "/api/fundednext/order";
}

function confirmFor(broker: LiveBroker, refs: ConfirmRefs): string {
  if (broker === "wsf") return refs.wsf || WSF_LIVE_CONFIRM;
  if (broker === "ftmo") return refs.ftmo || FTMO_LIVE_CONFIRM;
  if (broker === "alphacapital") return refs.acg || ALPHACAPITAL_LIVE_CONFIRM;
  if (broker === "fundingpips") return refs.fpips || FUNDINGPIPS_LIVE_CONFIRM;
  if (broker === "neomaa") return refs.neo || NEOMAA_LIVE_CONFIRM;
  if (broker === "fortraders") return refs.ftt || FORTRADERS_LIVE_CONFIRM;
  return refs.fn || FUNDEDNEXT_LIVE_CONFIRM;
}

function brokerForPendingReason(reason: string | undefined): LiveBroker | null {
  if (reason === WSF_LIVE_PENDING) return "wsf";
  if (reason === FUNDEDNEXT_LIVE_PENDING) return "fundednext";
  if (reason === ALPHACAPITAL_LIVE_PENDING) return "alphacapital";
  if (reason === FUNDINGPIPS_LIVE_PENDING) return "fundingpips";
  if (reason === NEOMAA_LIVE_PENDING) return "neomaa";
  if (reason === FORTRADERS_LIVE_PENDING) return "fortraders";
  return null;
}

function winePrefixFor(broker: LiveBroker): string {
  if (broker === "wsf") return ".mt5-wsf";
  if (broker === "ftmo") return ".mt5-ftmo";
  if (broker === "alphacapital") return ".mt5-alphacapital";
  if (broker === "fundingpips") return ".mt5-fundingpips";
  if (broker === "neomaa") return ".mt5-neomaa";
  if (broker === "fortraders") return ".mt5-fortraders";
  return ".mt5-fundednext";
}

type ConfirmRefs = {
  wsf: string;
  ftmo: string;
  fn: string;
  acg: string;
  fpips: string;
  neo: string;
  ftt: string;
};

async function closeLiveGroup(
  positionId: string,
  refs: ConfirmRefs,
  failures: string[]
): Promise<void> {
  const snapshot = getDeskSnapshot();
  const targets = liveGroupPositions(snapshot, positionId);
  for (const row of targets) {
    if (!row.liveBroker) continue;
    const symbol =
      row.liveBroker === "wsf" && row.symbol === "EURUSD" ? "EURUSDc" : row.symbol;
    const payload = await postLiveOrder(
      row.liveBroker,
      "close",
      confirmFor(row.liveBroker, refs),
      symbol,
      row.side
    );
    if (liveCloseAlreadyFlat(payload)) {
      flattenPosition(row.id);
    } else {
      const reason = payload.reason || `${row.liveBroker} live close failed`;
      markLiveCloseFailed(row.id, `${reason} — desk row kept`);
      failures.push(`${row.liveBroker}: ${reason}`);
    }
  }
}

async function postLiveOrder(
  broker: LiveBroker,
  action: "open" | "close",
  confirm: string,
  symbol: string,
  side: string
): Promise<LiveOrderResult> {
  const endpoint = endpointFor(broker, action);
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(LIVE_ORDER_CLIENT_BUDGET_MS),
      body: JSON.stringify({
        live: true,
        confirm,
        action,
        symbol,
        side,
        volume_min: true,
      }),
    });
    return (await response.json()) as LiveOrderResult;
  } catch (caught) {
    const timedOut =
      caught instanceof Error && (caught.name === "TimeoutError" || caught.name === "AbortError");
    return {
      ok: false,
      source: "seven-desk",
      endpoint,
      requestId: "",
      stage: timedOut ? "timeout" : action,
      reason: timedOut
        ? "client deadline — live order route returned no JSON"
        : caught instanceof Error
          ? caught.message
          : `${broker} ${action} failed`,
      login: null,
      server: null,
      winePrefix: winePrefixFor(broker),
    };
  }
}

export function DeskProvider({ children }: { children: React.ReactNode }) {
  const state = useSyncExternalStore(
    subscribeDesk,
    getDeskSnapshot,
    getServerDeskSnapshot
  );
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const timers = useRef<number[]>([]);
  const wsfConfirm = useRef("");
  const ftmoConfirm = useRef("");
  const fnConfirm = useRef("");
  const acgConfirm = useRef("");
  const fpipsConfirm = useRef("");
  const neoConfirm = useRef("");
  const fttConfirm = useRef("");

  useEffect(() => {
    const tick = window.setInterval(() => {
      patchDesk((current) =>
        applyQuoteMarks({
          ...current,
          quotes: nudgeQuotes(current.quotes),
        })
      );
    }, 2200);
    return () => window.clearInterval(tick);
  }, []);

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((id) => window.clearTimeout(id));
  }, []);

  const selectAccount = useCallback((id: string) => {
    selectAccountStore(id);
  }, []);

  const setMaster = useCallback((id: string) => {
    const account = getDeskSnapshot().accounts.find((row) => row.id === id);
    if (!account || account.firmId !== "ftmo") {
      ftmoConfirm.current = "";
      setFtmoLiveMasterStore(false);
    }
    setMasterStore(id);
  }, []);

  const updateAccount = useCallback(
    (id: string, accountPatch: Partial<TradingAccount>) => {
      updateAccountStore(id, accountPatch);
    },
    []
  );

  const setConnection = useCallback(
    (id: string, status: ConnectionStatus, reason?: string) => {
      setConnectionStore(id, status, reason);
    },
    []
  );

  const updateCopy = useCallback(
    (slaveAccountId: string, copyPatch: Partial<CopySettings>) => {
      updateCopyStore(slaveAccountId, copyPatch);
    },
    []
  );

  const setSymbolMap = useCallback(
    (slaveAccountId: string, masterSymbol: string, mapped: string) => {
      setSymbolMapStore(slaveAccountId, masterSymbol, mapped);
    },
    []
  );

  const setWsfLiveCopy = useCallback((enabled: boolean, confirm: string) => {
    if (enabled && confirm !== WSF_LIVE_CONFIRM) {
      return `Type ${WSF_LIVE_CONFIRM} to arm WSF live copy.`;
    }
    wsfConfirm.current = enabled ? confirm : "";
    setWsfLiveCopyStore(enabled);
    return null;
  }, []);

  const setFtmoLiveMaster = useCallback((enabled: boolean, confirm: string) => {
    if (enabled && confirm !== FTMO_LIVE_CONFIRM) {
      return `Type ${FTMO_LIVE_CONFIRM} to arm FTMO live master.`;
    }
    const master = getDeskSnapshot().accounts.find((row) => row.id === getDeskSnapshot().masterId);
    if (enabled && master?.firmId !== "ftmo") {
      return "Make FTMO the master before arming live master.";
    }
    ftmoConfirm.current = enabled ? confirm : "";
    setFtmoLiveMasterStore(enabled);
    return null;
  }, []);

  const setFundednextLiveCopy = useCallback((enabled: boolean, confirm: string) => {
    if (enabled && confirm !== FUNDEDNEXT_LIVE_CONFIRM) {
      return `Type ${FUNDEDNEXT_LIVE_CONFIRM} to arm FundedNext live copy.`;
    }
    fnConfirm.current = enabled ? confirm : "";
    setFundednextLiveCopyStore(enabled);
    return null;
  }, []);

  const setAlphacapitalLiveCopy = useCallback((enabled: boolean, confirm: string) => {
    if (enabled && confirm !== ALPHACAPITAL_LIVE_CONFIRM) {
      return `Type ${ALPHACAPITAL_LIVE_CONFIRM} to arm Alpha Capital live copy.`;
    }
    acgConfirm.current = enabled ? confirm : "";
    setAlphacapitalLiveCopyStore(enabled);
    return null;
  }, []);

  const setFundingpipsLiveCopy = useCallback((enabled: boolean, confirm: string) => {
    if (enabled && confirm !== FUNDINGPIPS_LIVE_CONFIRM) {
      return `Type ${FUNDINGPIPS_LIVE_CONFIRM} to arm FundingPips live copy.`;
    }
    fpipsConfirm.current = enabled ? confirm : "";
    setFundingpipsLiveCopyStore(enabled);
    return null;
  }, []);

  const setNeomaaLiveCopy = useCallback((enabled: boolean, confirm: string) => {
    if (enabled && confirm !== NEOMAA_LIVE_CONFIRM) {
      return `Type ${NEOMAA_LIVE_CONFIRM} to arm Neomaa live copy.`;
    }
    neoConfirm.current = enabled ? confirm : "";
    setNeomaaLiveCopyStore(enabled);
    return null;
  }, []);

  const setFortradersLiveCopy = useCallback((enabled: boolean, confirm: string) => {
    if (enabled && confirm !== FORTRADERS_LIVE_CONFIRM) {
      return `Type ${FORTRADERS_LIVE_CONFIRM} to arm Fortraders live copy.`;
    }
    fttConfirm.current = enabled ? confirm : "";
    setFortradersLiveCopyStore(enabled);
    return null;
  }, []);

  const fanOutLiveSlaves = useCallback(async (groupId: string) => {
    const refs = {
      wsf: wsfConfirm.current,
      ftmo: ftmoConfirm.current,
      fn: fnConfirm.current,
      acg: acgConfirm.current,
      fpips: fpipsConfirm.current,
      neo: neoConfirm.current,
      ftt: fttConfirm.current,
    };
    const pending = pendingLiveSlaveEvents(getDeskSnapshot(), groupId);
    for (const event of pending) {
      const broker = brokerForPendingReason(event.reason);
      if (!broker) continue;
      const symbol =
        broker === "wsf" && event.symbol === "EURUSD" ? "EURUSDc" : event.symbol;
      try {
        const payload = await postLiveOrder(
          broker,
          "open",
          confirmFor(broker, refs),
          symbol,
          event.side
        );
        applyLiveCopyResult(event.id, payload, broker);
      } catch (caught) {
        applyLiveCopyResult(
          event.id,
          {
            ok: false,
            source: "seven-desk",
            endpoint: endpointFor(broker, "open"),
            requestId: "",
            stage: "copy",
            reason: caught instanceof Error ? caught.message : `${broker} live copy failed`,
            login: null,
            server: null,
            winePrefix: winePrefixFor(broker),
          },
          broker
        );
      }
    }
  }, []);

  const placeTrade = useCallback((input: MasterTradeInput) => {
    const snapshot = getDeskSnapshot();
    const master = snapshot.accounts.find((row) => row.id === snapshot.masterId);
    if (snapshot.ftmoLiveMaster) {
      if (master?.firmId !== "ftmo") {
        return "FTMO live master is armed but FTMO is not the master.";
      }
      if (input.symbol !== "EURUSD" && input.symbol !== "EURUSDc") {
        return "FTMO live master is EURUSD min-lot only.";
      }
      setBusy(true);
      const handle = window.setTimeout(() => {
        void (async () => {
          try {
            const liveInput: MasterTradeInput = {
              ...input,
              symbol: "EURUSD",
              lots: 0.01,
            };
            const payload = await postLiveOrder(
              "ftmo",
              "open",
              ftmoConfirm.current || FTMO_LIVE_CONFIRM,
              "EURUSD",
              liveInput.side
            );
            const placed = placeLiveMaster(liveInput, payload, "ftmo");
            if (placed.groupId && !placed.error) {
              resolveGroup(placed.groupId);
              await fanOutLiveSlaves(placed.groupId);
            }
          } finally {
            setBusy(false);
          }
        })();
      }, 160);
      timers.current.push(handle);
      return null;
    }

    const result = placeTradeStore(input);
    if (result.groupId && !result.error) {
      setBusy(true);
      const handle = window.setTimeout(() => {
        void (async () => {
          resolveGroup(result.groupId!);
          await fanOutLiveSlaves(result.groupId!);
          setBusy(false);
        })();
      }, 160);
      timers.current.push(handle);
    }
    return result.error;
  }, [fanOutLiveSlaves]);

  const flatten = useCallback((positionId: string) => {
    const snapshot = getDeskSnapshot();
    const position = snapshot.positions.find((row) => row.id === positionId);
    if (!position) return "Position already closed.";
    if (!position.liveBroker) {
      setActionError(null);
      return flattenPosition(positionId);
    }
    const refs = {
      wsf: wsfConfirm.current,
      ftmo: ftmoConfirm.current,
      fn: fnConfirm.current,
      acg: acgConfirm.current,
      fpips: fpipsConfirm.current,
      neo: neoConfirm.current,
      ftt: fttConfirm.current,
    };
    setActionError(null);
    setBusy(true);
    void (async () => {
      const failures: string[] = [];
      try {
        await closeLiveGroup(positionId, refs, failures);
      } finally {
        setActionError(failures.length ? failures.join(" · ") : null);
        setBusy(false);
      }
    })();
    return null;
  }, []);

  const flattenAll = useCallback(() => {
    const snapshot = getDeskSnapshot();
    const { liveRepIds, paperIds } = flattenAllTargets(snapshot);
    if (liveRepIds.length === 0 && paperIds.length === 0) {
      return "No open positions.";
    }
    const refs = {
      wsf: wsfConfirm.current,
      ftmo: ftmoConfirm.current,
      fn: fnConfirm.current,
      acg: acgConfirm.current,
      fpips: fpipsConfirm.current,
      neo: neoConfirm.current,
      ftt: fttConfirm.current,
    };
    setActionError(null);
    if (liveRepIds.length === 0) {
      for (const id of paperIds) flattenPosition(id);
      return null;
    }
    setBusy(true);
    void (async () => {
      const failures: string[] = [];
      try {
        for (const id of liveRepIds) {
          const still = getDeskSnapshot().positions.some((row) => row.id === id);
          if (!still) continue;
          await closeLiveGroup(id, refs, failures);
        }
        for (const row of getDeskSnapshot().positions) {
          if (!row.liveBroker) flattenPosition(row.id);
        }
      } finally {
        setActionError(failures.length ? failures.join(" · ") : null);
        setBusy(false);
      }
    })();
    return null;
  }, []);

  const resetDemo = useCallback(() => {
    timers.current.forEach((id) => window.clearTimeout(id));
    timers.current = [];
    setBusy(false);
    setActionError(null);
    wsfConfirm.current = "";
    ftmoConfirm.current = "";
    fnConfirm.current = "";
    acgConfirm.current = "";
    fpipsConfirm.current = "";
    neoConfirm.current = "";
    fttConfirm.current = "";
    setWsfLiveCopyStore(false);
    setFtmoLiveMasterStore(false);
    setFundednextLiveCopyStore(false);
    setAlphacapitalLiveCopyStore(false);
    setFundingpipsLiveCopyStore(false);
    setNeomaaLiveCopyStore(false);
    setFortradersLiveCopyStore(false);
    resetDemoStore();
  }, []);

  const persistError = getPersistError();
  const api = useMemo<DeskApi>(
    () => ({
      hydration: persistError ? "error" : "ready",
      hydrateError: persistError,
      state,
      busy,
      actionError,
      selectAccount,
      setMaster,
      updateAccount,
      setConnection,
      updateCopy,
      setSymbolMap,
      placeTrade,
      flatten,
      flattenAll,
      resetDemo,
      setWsfLiveCopy,
      setFtmoLiveMaster,
      setFundednextLiveCopy,
      setAlphacapitalLiveCopy,
      setFundingpipsLiveCopy,
      setNeomaaLiveCopy,
      setFortradersLiveCopy,
    }),
    [
      persistError,
      state,
      busy,
      actionError,
      selectAccount,
      setMaster,
      updateAccount,
      setConnection,
      updateCopy,
      setSymbolMap,
      placeTrade,
      flatten,
      flattenAll,
      resetDemo,
      setWsfLiveCopy,
      setFtmoLiveMaster,
      setFundednextLiveCopy,
      setAlphacapitalLiveCopy,
      setFundingpipsLiveCopy,
      setNeomaaLiveCopy,
      setFortradersLiveCopy,
    ]
  );

  return <DeskContext.Provider value={api}>{children}</DeskContext.Provider>;
}

export function useDesk(): DeskApi {
  const value = useContext(DeskContext);
  if (!value) throw new Error("useDesk must be used inside DeskProvider");
  return value;
}
