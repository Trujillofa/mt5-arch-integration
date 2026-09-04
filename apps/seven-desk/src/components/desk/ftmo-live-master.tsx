"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useDesk } from "@/lib/desk-context";
import { FTMO_LIVE_CONFIRM } from "@/lib/ftmo/types";

export function FtmoLiveMaster() {
  const { state, setFtmoLiveMaster } = useDesk();
  const [ack, setAck] = useState(false);
  const [confirm, setConfirm] = useState("");

  const master = state.accounts.find((row) => row.id === state.masterId);
  const ftmoIsMaster = master?.firmId === "ftmo";
  const armed = state.ftmoLiveMaster;
  const canArm = ack && confirm === FTMO_LIVE_CONFIRM && ftmoIsMaster;
  const hint = useMemo(() => {
    if (!ftmoIsMaster) return "Make FTMO the master before arming a live master fill.";
    if (armed) {
      return "Armed. Place master trade sends 0.01 EURUSD on FTMO 541163357. Copies wait until that fill.";
    }
    if (!ack) return "Tick the acknowledgement. This is a real FTMO order.";
    if (confirm !== FTMO_LIVE_CONFIRM) return `Type ${FTMO_LIVE_CONFIRM} exactly.`;
    return "Enable the switch to arm live master.";
  }, [armed, ack, confirm, ftmoIsMaster]);

  function onToggle(value: boolean) {
    if (!value) {
      setFtmoLiveMaster(false, "");
      setAck(false);
      setConfirm("");
      return;
    }
    const error = setFtmoLiveMaster(true, confirm);
    if (error) toast.error(error);
  }

  return (
    <section className="space-y-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
      <div>
        <p className="text-[11px] font-medium tracking-wide text-amber-100 uppercase">
          FTMO live master
        </p>
        <p className="text-xs text-muted-foreground">
          When armed, Place master trade is a real min-lot{" "}
          <span className="font-mono">POST /api/ftmo/order</span> on login 541163357.
          Slaves copy only after that fill. Not Vantage, not FP.
        </p>
      </div>

      <label className="flex items-start gap-2 text-xs text-amber-100/90">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={ack}
          onChange={(event) => {
            setAck(event.target.checked);
            if (!event.target.checked && armed) setFtmoLiveMaster(false, "");
          }}
        />
        <span>Send the master ticket as a live 0.01 EURUSD order on FTMO 541163357.</span>
      </label>

      <div className="space-y-1.5">
        <Label htmlFor="ftmo-master-confirm">Confirm token</Label>
        <Input
          id="ftmo-master-confirm"
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
          placeholder={FTMO_LIVE_CONFIRM}
          autoComplete="off"
          spellCheck={false}
          className="font-mono"
          disabled={armed}
        />
      </div>

      <div className="flex items-center justify-between gap-3">
        <Label htmlFor="ftmo-live-master" className="text-xs">
          Arm live master
        </Label>
        <Switch
          id="ftmo-live-master"
          checked={armed}
          disabled={!canArm && !armed}
          onCheckedChange={(value) => onToggle(Boolean(value))}
        />
      </div>

      <p className="text-xs text-muted-foreground">{hint}</p>
    </section>
  );
}
