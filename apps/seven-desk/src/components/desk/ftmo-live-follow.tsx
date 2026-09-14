"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useDesk } from "@/lib/desk-context";
import { FTMO_LIVE_CONFIRM } from "@/lib/ftmo/types";

export function FtmoLiveFollow() {
  const { state, setFtmoFollowTerminal } = useDesk();
  const [ack, setAck] = useState(false);
  const [confirm, setConfirm] = useState("");

  const master = state.accounts.find((row) => row.id === state.masterId);
  const ftmoIsMaster = master?.firmId === "ftmo";
  const armed = state.ftmoFollowTerminal;
  const canArm = ack && confirm === FTMO_LIVE_CONFIRM && ftmoIsMaster;
  const hint = useMemo(() => {
    if (!ftmoIsMaster) return "Make FTMO the master before arming terminal follow.";
    if (armed) {
      return "Armed. Only new FTMO terminal tickets copy to armed slaves. Closes and later SL/TP edits follow. Leftovers at arm stay uncopied. Refresh turns this off.";
    }
    if (!ack) return "Tick the acknowledgement. New terminal tickets copy live onto armed slaves.";
    if (confirm !== FTMO_LIVE_CONFIRM) return `Type ${FTMO_LIVE_CONFIRM} exactly.`;
    return "Enable the switch to follow new FTMO terminal tickets.";
  }, [armed, ack, confirm, ftmoIsMaster]);

  function onToggle(value: boolean) {
    if (!value) {
      setFtmoFollowTerminal(false, "");
      setAck(false);
      setConfirm("");
      return;
    }
    const error = setFtmoFollowTerminal(true, confirm);
    if (error) toast.error(error);
  }

  return (
    <section className="space-y-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
      <div>
        <p className="text-[11px] font-medium tracking-wide text-amber-100 uppercase">
          FTMO terminal follow
        </p>
        <p className="text-xs text-muted-foreground">
          When armed, new clicks in the FTMO terminal (market and pending) copy onto armed
          live slaves. Later SL/TP edits fan out. When the FTMO ticket is gone, the slave
          group closes or cancels. Does not OrderSend on FTMO. Tickets already open at arm
          stay leftovers. Session-only — a refresh disarms.
        </p>
      </div>

      <label className="flex items-start gap-2 text-xs text-amber-100/90">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={ack}
          onChange={(event) => {
            setAck(event.target.checked);
            if (!event.target.checked && armed) setFtmoFollowTerminal(false, "");
          }}
        />
        <span>
          Follow new FTMO 541163357 terminal tickets onto armed slaves. Not leftovers, not
          Place master, not Alpha.
        </span>
      </label>

      <div className="space-y-1.5">
        <Label htmlFor="ftmo-follow-confirm">Confirm token</Label>
        <Input
          id="ftmo-follow-confirm"
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
        <Label htmlFor="ftmo-live-follow" className="text-xs">
          Arm terminal follow
        </Label>
        <Switch
          id="ftmo-live-follow"
          checked={armed}
          disabled={!canArm && !armed}
          onCheckedChange={(value) => onToggle(Boolean(value))}
        />
      </div>

      <p className="text-xs text-muted-foreground">{hint}</p>
    </section>
  );
}
