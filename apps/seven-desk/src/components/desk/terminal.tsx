"use client";

import { AccountStrip } from "@/components/desk/account-strip";
import { BlotterTable } from "@/components/desk/blotter-table";
import { CopyPanel } from "@/components/desk/copy-panel";
import { ExposurePanel, PositionsPanel } from "@/components/desk/positions-panel";
import { TradeTicket } from "@/components/desk/trade-ticket";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useDesk } from "@/lib/desk-context";
import { FIRM_BY_ID } from "@/lib/firms";
import { formatMoney } from "@/lib/format";

export function Terminal() {
  const { hydration, hydrateError, state, setMaster, resetDemo } = useDesk();
  const master = state.accounts.find((account) => account.id === state.masterId);
  const paperBooks = state.accounts.filter(
    (account) => account.status === "connected"
  ).length;
  const float = state.positions.reduce((sum, position) => sum + position.pnl, 0);

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b border-foreground/10 bg-card/70 backdrop-blur">
        <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-3 px-4 py-3 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex size-8 items-center justify-center rounded-md bg-foreground text-background">
              <span className="font-mono text-xs font-bold">7D</span>
            </div>
            <div>
              <h1 className="font-heading text-sm font-semibold tracking-tight md:text-base">
                Seven Desk
              </h1>
              <p className="text-xs text-muted-foreground">
                Own-account copy terminal · paper adapters
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 md:gap-3">
            <span className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 font-mono text-[11px] text-emerald-300">
              PAPER
            </span>
            <span className="hidden font-mono text-[11px] text-muted-foreground sm:inline">
              {paperBooks}/7 connected
            </span>
            <span className="hidden font-mono text-[11px] text-muted-foreground md:inline">
              float {float >= 0 ? "+" : ""}
              {float.toFixed(2)}
            </span>
            <div className="flex items-center gap-2">
              <span className="text-[11px] tracking-wide text-muted-foreground uppercase">
                Master
              </span>
              <Select
                value={state.masterId}
                onValueChange={(value) => setMaster(String(value))}
              >
                <SelectTrigger className="h-8 min-w-[180px]" size="sm">
                  <SelectValue>
                    {master
                      ? `${FIRM_BY_ID[master.firmId].name} · ${master.login}`
                      : "Select master"}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {state.accounts.map((account) => (
                    <SelectItem key={account.id} value={account.id}>
                      {FIRM_BY_ID[account.firmId].name} · {account.login}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={resetDemo}>
              Reset demo
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-[1400px] flex-1 flex-col gap-4 px-4 py-4">
        {hydrateError ? (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
            {hydrateError}
          </div>
        ) : null}

        {hydration === "error" && !hydrateError ? (
          <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
            Desk failed to load. Reset the demo book to continue.
          </div>
        ) : null}

        <section className="space-y-2">
          <div className="flex items-end justify-between">
            <h2 className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
              Accounts
            </h2>
            {master ? (
              <p className="font-mono text-[11px] text-muted-foreground">
                Master equity {formatMoney(master.equity)}
              </p>
            ) : null}
          </div>
          <AccountStrip />
        </section>

        <section className="grid gap-4 lg:grid-cols-2">
          <TradeTicket />
          <CopyPanel />
        </section>

        <section className="overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10">
          <Tabs defaultValue="blotter">
            <div className="flex items-center justify-between gap-3 border-b px-3 pt-2">
              <TabsList variant="line" className="w-full justify-start md:w-auto">
                <TabsTrigger value="blotter">Blotter</TabsTrigger>
                <TabsTrigger value="positions">Positions</TabsTrigger>
                <TabsTrigger value="exposure">Exposure</TabsTrigger>
              </TabsList>
            </div>
            <TabsContent value="blotter">
              <BlotterTable />
            </TabsContent>
            <TabsContent value="positions">
              <PositionsPanel />
            </TabsContent>
            <TabsContent value="exposure">
              <ExposurePanel />
            </TabsContent>
          </Tabs>
        </section>
      </main>
    </div>
  );
}
