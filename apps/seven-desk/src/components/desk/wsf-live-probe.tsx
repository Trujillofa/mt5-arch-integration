"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useDesk } from "@/lib/desk-context";
import { ACCOUNT_IDS } from "@/lib/seed";
import type {
  WsfConnectionStatus,
  WsfDealRow,
  WsfFetchedAccount,
  WsfLiveReport,
  WsfPlatformProbe,
  WsfPositionRow,
} from "@/lib/wsf/types";

let lastReport: WsfLiveReport | null = null;

export function WsfLiveProbe() {
  const { updateAccount } = useDesk();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<WsfLiveReport | null>(lastReport);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/wsf/probe", { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Probe failed (${response.status})`);
      }
      const next = (await response.json()) as WsfLiveReport;
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
    // One auto-fetch on mount so the WSF card picks up operator env.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section className="space-y-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-medium tracking-wide text-amber-200 uppercase">
            Live WSF fetch
          </p>
          <p className="text-xs text-muted-foreground">
            Read-only snapshot. Uses operator MT5 env when present
            (login/server only on the server). Copy execution stays paper.
            Live min-lot send is WSF live copy on this card (or the scratch control).
          </p>
        </div>
        <Button type="button" size="sm" disabled={busy} onClick={run}>
          {busy ? "Fetching…" : "Fetch WSF"}
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
  report: WsfLiveReport,
  updateAccount: (id: string, patch: { login?: string; server?: string; platform?: string; balance?: number; equity?: number }) => void
) {
  const personal =
    report.books.find((book) => book.source === "mt5-env") ||
    report.books.find((book) => book.kind === "personal-env");
  const login = personal?.login || report.identity.login;
  const server = personal?.broker || report.identity.server;
  if (!login && !server) return;
  updateAccount(ACCOUNT_IDS.wsf, {
    ...(login ? { login } : {}),
    ...(server ? { server } : {}),
    platform: "MT5",
    ...(personal?.balance != null ? { balance: personal.balance } : {}),
    ...(personal?.equity != null ? { equity: personal.equity } : {}),
  });
}

function connectionCopy(status: WsfConnectionStatus): { label: string; className: string } {
  switch (status) {
    case "connected":
      return { label: "connected", className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-200" };
    case "auth_failed":
      return { label: "auth failed", className: "border-rose-500/30 bg-rose-500/10 text-rose-200" };
    case "missing_wine":
      return { label: "still missing Wine", className: "border-amber-500/30 bg-amber-500/10 text-amber-100" };
    case "password_missing":
      return { label: "password missing", className: "border-amber-500/30 bg-amber-500/10 text-amber-100" };
    default:
      return { label: "no credentials", className: "border-foreground/15 bg-background/40 text-muted-foreground" };
  }
}

function ReportView({ report }: { report: WsfLiveReport }) {
  const status = connectionCopy(report.connectionStatus ?? "missing_wine");
  const login = report.login ?? report.identity.login;
  const server = report.server ?? report.identity.server;
  return (
    <div className="space-y-3 text-xs">
      <p className={`rounded-md border px-2 py-1.5 font-medium ${status.className}`}>
        Fetch result: {status.label}
        {login ? ` · MT5 ${login}` : ""}
        {server ? ` @ ${server}` : ""}
        {report.balance != null ? ` · bal ${report.balance.toLocaleString()}` : " · bal —"}
        {report.equity != null ? ` · eq ${report.equity.toLocaleString()}` : ""}
      </p>
      <p className="text-muted-foreground">
        Source {report.source}
        {report.usedOperatorEnv ? " · operator env" : report.homepageOk ? " · homepage ok" : ""}
        {report.usedOfficialDemoCard ? " · official demo card" : ""}
        {report.identity.login ? ` · MT5 ${report.identity.login}` : ""}
        {report.identity.server ? ` @ ${report.identity.server}` : ""}
        {report.identity.email ? ` · ${report.identity.email}` : ""}
        {report.identity.hasPassword ? " · password present" : " · password missing"}
        {report.winePrefixPresent ? " · Wine prefix on disk" : " · Wine prefix missing"}
        {report.fileBridgePresent ? " · file bridge live" : " · file bridge missing"}
      </p>
      <p className="rounded-md border border-amber-500/20 bg-background/40 px-2 py-1.5 text-amber-100/90">
        {report.bookHonesty}
      </p>
      <BooksTable books={report.books} />
      <HistoryBlock
        positions={report.openPositions}
        deals={report.recentDeals}
        connectionStatus={report.connectionStatus ?? "missing_wine"}
      />
      <ul className="space-y-1.5">
        {report.platforms.map((row) => (
          <li key={row.platform} className="rounded-md bg-background/40 px-2 py-1.5">
            <p className="font-medium tracking-wide uppercase">{row.platform}</p>
            <p className="font-mono text-[11px] text-muted-foreground">
              {statusLabel(row)} · HTTP {row.httpStatus ?? "—"}
              {row.publicLogin ? ` · ${row.publicLogin}` : ""}
              {row.publicServer ? ` @ ${row.publicServer}` : ""}
            </p>
            <p className="mt-0.5 text-muted-foreground">{row.detail}</p>
          </li>
        ))}
      </ul>
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
        <p className="text-emerald-300">Live auth succeeded on at least one path.</p>
      )}
    </div>
  );
}

function BooksTable({ books }: { books: WsfFetchedAccount[] }) {
  if (!books.length) {
    return (
      <p className="text-muted-foreground">
        No trading books were returned after login.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto rounded-md bg-background/40">
      <table className="w-full min-w-[520px] text-left">
        <caption className="sr-only">Fetched WSF-reachable trading books</caption>
        <thead>
          <tr className="text-[10px] tracking-wide text-muted-foreground uppercase">
            <th className="px-2 py-1.5 font-medium">Broker</th>
            <th className="px-2 py-1.5 font-medium">Login</th>
            <th className="px-2 py-1.5 font-medium">Name</th>
            <th className="px-2 py-1.5 font-medium">Balance</th>
            <th className="px-2 py-1.5 font-medium">Ccy</th>
            <th className="px-2 py-1.5 font-medium">Lev</th>
          </tr>
        </thead>
        <tbody>
          {books.map((book) => (
            <tr key={`${book.source}-${book.accountId}`} className="border-t border-foreground/10">
              <td className="px-2 py-1.5">
                {book.broker}
                <span className="mt-0.5 block text-[10px] text-amber-200/80">
                  {book.kind === "personal-env"
                    ? "operator env"
                    : book.plantIsWsf
                      ? "WSF plant"
                      : "not WSF plant"}
                </span>
              </td>
              <td className="px-2 py-1.5 font-mono">{book.login}</td>
              <td className="px-2 py-1.5 text-muted-foreground">{book.name}</td>
              <td className="px-2 py-1.5 font-mono tabular-nums">
                {book.balance == null ? "—" : book.balance.toLocaleString()}
              </td>
              <td className="px-2 py-1.5 font-mono">{book.currency ?? "—"}</td>
              <td className="px-2 py-1.5 font-mono">{book.leverage ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HistoryBlock({
  positions,
  deals,
  connectionStatus,
}: {
  positions: WsfPositionRow[];
  deals: WsfDealRow[];
  connectionStatus: WsfConnectionStatus;
}) {
  return (
    <div className="space-y-1.5 rounded-md bg-background/40 px-2 py-1.5 text-muted-foreground">
      <p>
        Open positions:{" "}
        <span className="font-mono text-foreground">{positions.length}</span>
        {" · "}
        Recent deals:{" "}
        <span className="font-mono text-foreground">{deals.length}</span>
      </p>
      {positions.length === 0 && deals.length === 0 ? (
        <p>
          {connectionStatus === "connected"
            ? "No open positions or recent deals in the live snapshot."
            : connectionStatus === "missing_wine"
              ? "No live history. Password is loaded; Wine prefix / Mt5ArchBridge is still missing on this host."
              : connectionStatus === "auth_failed"
                ? "No live history. A terminal was present but the snapshot/auth path did not return books."
                : "No live history. Need an MT5 password + MetaAPI token, or a file-backend snapshot from a logged-in terminal."}
        </p>
      ) : (
        <ul className="space-y-1">
          {positions.slice(0, 8).map((row, index) => (
            <li key={`p-${row.accountLogin}-${row.symbol}-${index}`} className="font-mono">
              pos {row.accountLogin} {row.side} {row.symbol} vol {row.volume ?? "—"}
            </li>
          ))}
          {deals.slice(0, 8).map((row, index) => (
            <li key={`d-${row.accountLogin}-${row.symbol}-${index}`} className="font-mono">
              deal {row.accountLogin} {row.side} {row.symbol} @ {row.price ?? "—"}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function statusLabel(row: WsfPlatformProbe): string {
  if (row.authenticated) return "authenticated";
  if (row.reachable) return "reachable";
  return "blocked";
}
