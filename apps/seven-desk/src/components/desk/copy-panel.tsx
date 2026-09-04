"use client";

import { ConnectionPill } from "@/components/desk/status-pills";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { defaultCopySettings } from "@/lib/copy-engine";
import { useDesk } from "@/lib/desk-context";
import { FIRM_BY_ID } from "@/lib/firms";
import { MASTER_SYMBOLS } from "@/lib/quotes";
import { FundedNextLiveCopy } from "@/components/desk/fundednext-live-copy";
import { FundedNextLiveProbe } from "@/components/desk/fundednext-live-probe";
import { FtmoLiveMaster } from "@/components/desk/ftmo-live-master";
import { FtmoLiveProbe } from "@/components/desk/ftmo-live-probe";
import { WsfLiveProbe } from "@/components/desk/wsf-live-probe";
import { WsfLiveCopy } from "@/components/desk/wsf-live-copy";
import { WsfLiveScratch } from "@/components/desk/wsf-live-scratch";

export function CopyPanel() {
  const {
    state,
    updateAccount,
    setConnection,
    setMaster,
    updateCopy,
    setSymbolMap,
  } = useDesk();

  const account = state.accounts.find(
    (row) => row.id === state.selectedAccountId
  );
  if (!account) {
    return (
      <Card size="sm" className="h-full">
        <CardHeader>
          <CardTitle>Account</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Select an account from the strip to edit connection or copy rules.
          </p>
        </CardContent>
      </Card>
    );
  }

  const firm = FIRM_BY_ID[account.firmId];
  const isMaster = account.id === state.masterId;
  const copy =
    state.copySettings.find((row) => row.slaveAccountId === account.id) ??
    defaultCopySettings(account.id);

  return (
    <Card size="sm" className="h-full">
      <CardHeader className="border-b">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>
              {firm.name}
              {isMaster ? " · master" : " · slave"}
            </CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">{firm.notes}</p>
          </div>
          <ConnectionPill status={account.status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-5 pt-4">
        <section className="space-y-3">
          <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            Connection (paper)
          </p>
          <div className="grid grid-cols-2 gap-3">
            <TextField
              id="login"
              label="Login / account id"
              value={account.login}
              onChange={(value) => updateAccount(account.id, { login: value })}
            />
            <TextField
              id="platform"
              label="Platform"
              value={account.platform}
              onChange={(value) => updateAccount(account.id, { platform: value })}
            />
            <TextField
              id="server"
              label="Server"
              value={account.server}
              onChange={(value) => updateAccount(account.id, { server: value })}
            />
            <TextField
              id="label"
              label="Desk label"
              value={account.label}
              onChange={(value) => updateAccount(account.id, { label: value })}
            />
          </div>
          <p className="font-mono text-[11px] text-muted-foreground">
            Typical: {firm.platforms.join(" · ")} · {firm.typicalServer}
          </p>
          <div className="flex flex-wrap gap-2">
            {account.status === "connected" ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setConnection(account.id, "disconnected")}
              >
                Disconnect
              </Button>
            ) : (
              <Button
                type="button"
                size="sm"
                onClick={() => setConnection(account.id, "connected")}
              >
                Connect paper
              </Button>
            )}
            {!isMaster ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setMaster(account.id)}
              >
                Make master
              </Button>
            ) : null}
          </div>
        </section>

        {account.firmId === "wsf" ? (
          <>
            <WsfLiveProbe />
            <WsfLiveCopy />
            <WsfLiveScratch />
          </>
        ) : null}

        {account.firmId === "fundednext" ? (
          <>
            <FundedNextLiveProbe />
            <FundedNextLiveCopy />
          </>
        ) : null}

        {account.firmId === "ftmo" ? (
          <>
            <FtmoLiveProbe />
            <FtmoLiveMaster />
          </>
        ) : null}

        {isMaster ? (
          <p className="rounded-lg bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
            This account is the source. Child sizing, mapping, and skips are
            configured on each slave — pick another card in the strip.
          </p>
        ) : (
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                  Copy rules
                </p>
                <p className="text-xs text-muted-foreground">
                  Normal risk controls. Empty map = same symbol. Blank map value
                  skips as unmapped.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Label htmlFor="copy-enabled" className="text-xs">
                  Enabled
                </Label>
                <Switch
                  id="copy-enabled"
                  checked={copy.enabled}
                  onCheckedChange={(checked) =>
                    updateCopy(account.id, { enabled: Boolean(checked) })
                  }
                />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <NumberField
                id="mult"
                label="Lot ×"
                value={copy.lotMultiplier}
                step="0.1"
                onChange={(value) =>
                  updateCopy(account.id, { lotMultiplier: value })
                }
              />
              <NumberField
                id="maxlot"
                label="Max lot"
                value={copy.maxLot}
                step="0.1"
                onChange={(value) => updateCopy(account.id, { maxLot: value })}
              />
              <NumberField
                id="slip"
                label="Max slip (pips)"
                value={copy.maxSlippagePips}
                step="0.1"
                onChange={(value) =>
                  updateCopy(account.id, { maxSlippagePips: value })
                }
              />
            </div>

            <div className="flex flex-wrap gap-5">
              <Toggle
                id="sltp"
                label="Copy SL / TP"
                checked={copy.copySlTp}
                onChange={(checked) =>
                  updateCopy(account.id, { copySlTp: checked })
                }
              />
              <Toggle
                id="reverse"
                label="Reverse side"
                checked={copy.reverse}
                onChange={(checked) =>
                  updateCopy(account.id, { reverse: checked })
                }
              />
            </div>

            <div className="space-y-2">
              <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                Symbol map
              </p>
              <div className="grid gap-2">
                {MASTER_SYMBOLS.map((symbol) => {
                  const mapped = Object.prototype.hasOwnProperty.call(
                    copy.symbolMap,
                    symbol
                  )
                    ? copy.symbolMap[symbol]
                    : symbol;
                  return (
                    <div
                      key={symbol}
                      className="grid grid-cols-[88px_1fr] items-center gap-2"
                    >
                      <span className="font-mono text-xs text-muted-foreground">
                        {symbol}
                      </span>
                      <Input
                        aria-label={`Map ${symbol}`}
                        value={mapped}
                        placeholder="unmapped"
                        className="h-7 font-mono text-xs"
                        onChange={(event) =>
                          setSymbolMap(account.id, symbol, event.target.value)
                        }
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          </section>
        )}
      </CardContent>
    </Card>
  );
}

function TextField({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="font-mono"
      />
    </div>
  );
}

function NumberField({
  id,
  label,
  value,
  step,
  onChange,
}: {
  id: string;
  label: string;
  value: number;
  step: string;
  onChange: (value: number) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type="number"
        step={step}
        min="0"
        value={Number.isFinite(value) ? String(value) : ""}
        className="font-mono"
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </div>
  );
}

function Toggle({
  id,
  label,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={(value) => onChange(Boolean(value))}
      />
      <Label htmlFor={id} className="text-xs font-normal">
        {label}
      </Label>
    </div>
  );
}
