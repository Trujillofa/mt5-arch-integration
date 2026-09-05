"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useDesk } from "@/lib/desk-context";
import {
  FORTRADERS_EXPECTED_LOGIN,
  FORTRADERS_EXPECTED_SERVER,
  type FortradersConnectionStatus,
  type FortradersLiveReport,
} from "@/lib/fortraders/types";
import { ACCOUNT_IDS } from "@/lib/seed";

let lastReport: FortradersLiveReport | null = null;

export function FortradersLiveProbe() {
  const { updateAccount } = useDesk();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<FortradersLiveReport | null>(lastReport);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/fortraders/probe", { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Probe failed (${response.status})`);
      }
      const next = (await response.json()) as FortradersLiveReport;
      lastReport = next;
      setReport(next);
      applyToDesk(next, updateAccount);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Probe failed.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    const handle = window.setTimeout(() => {
      if (lastReport) {
        applyToDesk(lastReport, updateAccount);
        return;
      }
      void run();
    }, 0);
    return () => window.clearTimeout(handle);
    // One auto-fetch on mount so the Fortraders card picks up 737150.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section className="space-y-3 rounded-lg border border-sky-500/20 bg-sky-500/5 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-medium tracking-wide text-sky-200 uppercase">
            Live Fortraders fetch
          </p>
          <p className="text-xs text-muted-foreground">
            Read-only snapshot for {FORTRADERS_EXPECTED_LOGIN} @{" "}
            {FORTRADERS_EXPECTED_SERVER}. Snapshot is read-only. Live OrderSend
            is the Fortraders live copy control below. This challenge is MT5,
            not TradeLocker.
          </p>
        </div>
        <Button type="button" size="sm" disabled={busy} onClick={run}>
          {busy ? "Fetching…" : "Fetch Fortraders"}
        </Button>
      </div>
      {error ? (
        <p className="rounded-md border border-rose-500/30 bg-rose-500/10 px-2 py-1.5 text-xs text-rose-300">
          {error}
        </p>
      ) : null}
      {report ? <ReportView report={report} /> : null}
    </section>
  );
}

function applyToDesk(
  report: FortradersLiveReport,
  updateAccount: (
    id: string,
    patch: {
      login?: string;
      server?: string;
      platform?: string;
      balance?: number;
      equity?: number;
      label?: string;
    }
  ) => void
) {
  const login = report.login || FORTRADERS_EXPECTED_LOGIN;
  const server = report.server || FORTRADERS_EXPECTED_SERVER;
  if (login !== FORTRADERS_EXPECTED_LOGIN) return;
  updateAccount(ACCOUNT_IDS.fortraders, {
    login,
    server,
    platform: "MT5",
    ...(report.connectionStatus === "connected" && report.balance != null
      ? { balance: report.balance }
      : {}),
    ...(report.connectionStatus === "connected" && report.equity != null
      ? { equity: report.equity }
      : {}),
  });
}

function connectionCopy(status: FortradersConnectionStatus): {
  label: string;
  className: string;
} {
  switch (status) {
    case "connected":
      return {
        label: "connected",
        className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-200",
      };
    case "wrong_account":
      return {
        label: "wrong account",
        className: "border-rose-500/30 bg-rose-500/10 text-rose-200",
      };
    case "auth_failed":
      return {
        label: "auth failed",
        className: "border-rose-500/30 bg-rose-500/10 text-rose-200",
      };
    case "missing_wine":
      return {
        label: "file-bridge missing",
        className: "border-amber-500/30 bg-amber-500/10 text-amber-100",
      };
    case "password_missing":
      return {
        label: "password missing",
        className: "border-amber-500/30 bg-amber-500/10 text-amber-100",
      };
    default:
      return {
        label: "no credentials",
        className: "border-foreground/15 bg-background/40 text-muted-foreground",
      };
  }
}

function ReportView({ report }: { report: FortradersLiveReport }) {
  const status = connectionCopy(report.connectionStatus);
  return (
    <div className="space-y-3 text-xs">
      <p className={`rounded-md border px-2 py-1.5 font-medium ${status.className}`}>
        Fetch result: {status.label}
        {report.login ? ` · MT5 ${report.login}` : ""}
        {report.server ? ` @ ${report.server}` : ""}
        {report.balance != null ? ` · bal ${report.balance.toLocaleString()}` : " · bal —"}
        {report.equity != null ? ` · eq ${report.equity.toLocaleString()}` : ""}
      </p>
      <p className="rounded-md border border-sky-500/20 bg-background/40 px-2 py-1.5 text-sky-100/90">
        {report.bookHonesty}
      </p>
      {report.fetchNotes.length ? (
        <ul className="space-y-1 text-muted-foreground">
          {report.fetchNotes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
      {report.nextSecretNeeded ? (
        <p className="text-amber-200/90">Still needed: {report.nextSecretNeeded}</p>
      ) : (
        <p className="text-emerald-300">Live Fortraders snapshot is readable.</p>
      )}
    </div>
  );
}
