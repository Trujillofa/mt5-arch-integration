"use client";

import { ConnectionPill } from "@/components/desk/status-pills";
import { FIRM_ACCENT, FIRM_BY_ID } from "@/lib/firms";
import { compactNumber, formatMoney } from "@/lib/format";
import { useDesk } from "@/lib/desk-context";
import { cn } from "@/lib/utils";

export function AccountStrip() {
  const { state, selectAccount } = useDesk();

  return (
    <div className="-mx-4 flex gap-3 overflow-x-auto px-4 pb-1 md:mx-0 md:grid md:grid-cols-2 md:overflow-visible md:px-0 xl:grid-cols-7">
      {state.accounts.map((account) => {
        const firm = FIRM_BY_ID[account.firmId];
        const selected = state.selectedAccountId === account.id;
        const isMaster = state.masterId === account.id;
        const copy = state.copySettings.find(
          (row) => row.slaveAccountId === account.id
        );
        return (
          <button
            key={account.id}
            type="button"
            data-account={account.firmId}
            onClick={() => selectAccount(account.id)}
            className={cn(
              "w-[232px] shrink-0 rounded-xl bg-card text-left ring-1 transition-colors md:w-full",
              selected
                ? "ring-foreground/35"
                : "ring-foreground/10 hover:ring-foreground/20"
            )}
          >
            <div className={cn("h-1 rounded-t-xl", FIRM_ACCENT[account.firmId])} />
            <div className="space-y-3 p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                    {firm.name}
                  </p>
                  <p className="font-heading text-sm leading-tight">{account.label}</p>
                </div>
                {isMaster ? (
                  <span className="rounded-md bg-foreground px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-wide text-background uppercase">
                    Master
                  </span>
                ) : copy && !copy.enabled ? (
                  <span className="rounded-md bg-amber-500/15 px-1.5 py-0.5 font-mono text-[10px] tracking-wide text-amber-300 uppercase">
                    Copy off
                  </span>
                ) : null}
              </div>
              <div className="flex items-center justify-between gap-2">
                <ConnectionPill status={account.status} />
                <p className="font-mono text-xs text-muted-foreground">
                  {account.platform}
                </p>
              </div>
              <div className="flex items-end justify-between">
                <div>
                  <p className="text-[10px] tracking-wide text-muted-foreground uppercase">
                    Equity
                  </p>
                  <p className="font-mono text-sm tabular-nums">
                    {formatMoney(account.equity)}
                  </p>
                </div>
                <p className="font-mono text-[11px] text-muted-foreground">
                  #{account.login} · {compactNumber(account.balance)}
                </p>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
