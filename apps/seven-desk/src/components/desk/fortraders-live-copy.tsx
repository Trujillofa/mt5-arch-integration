"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useDesk } from "@/lib/desk-context";
import { FORTRADERS_LIVE_CONFIRM } from "@/lib/fortraders/types";

export function FortradersLiveCopy() {
  const { state, setFortradersLiveCopy } = useDesk();
  const [ack, setAck] = useState(false);
  const [confirm, setConfirm] = useState("");

  const armed = state.fortradersLiveCopy;
  const canArm = ack && confirm === FORTRADERS_LIVE_CONFIRM;
  const hint = useMemo(() => {
    if (armed) {
      return "Armed. Each master fill copies to Fortraders 737150 as 0.01 EURUSD.";
    }
    if (!ack) return "Tick the acknowledgement. This is a real Fortraders order on each master fill.";
    if (confirm !== FORTRADERS_LIVE_CONFIRM) return `Type ${FORTRADERS_LIVE_CONFIRM} exactly.`;
    return "Enable the switch to arm live copy.";
  }, [armed, ack, confirm]);

  function onToggle(value: boolean) {
    if (!value) {
      setFortradersLiveCopy(false, "");
      setAck(false);
      setConfirm("");
      return;
    }
    const error = setFortradersLiveCopy(true, confirm);
    if (error) toast.error(error);
  }

  return (
    <section className="space-y-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
      <div>
        <p className="text-[11px] font-medium tracking-wide text-amber-100 uppercase">
          Fortraders live copy
        </p>
        <p className="text-xs text-muted-foreground">
          When armed, Place master trade sends the Fortraders slave through{" "}
          <span className="font-mono">POST /api/fortraders/order</span> (open, min
          lot, login 737150). Other non-armed slaves stay paper. Not FTMO.
        </p>
      </div>

      <label className="flex items-start gap-2 text-xs text-amber-100/90">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={ack}
          onChange={(event) => {
            setAck(event.target.checked);
            if (!event.target.checked && armed) setFortradersLiveCopy(false, "");
          }}
        />
        <span>
          Copy each master fill to live Fortraders 737150 at 0.01 lot. Not
          FTMO, not FP Markets, not FundingPips.
        </span>
      </label>

      <div className="space-y-1.5">
        <Label htmlFor="fortraders-copy-confirm">Confirm token</Label>
        <Input
          id="fortraders-copy-confirm"
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
          placeholder={FORTRADERS_LIVE_CONFIRM}
          autoComplete="off"
          spellCheck={false}
          className="font-mono"
          disabled={armed}
        />
      </div>

      <div className="flex items-center justify-between gap-3">
        <Label htmlFor="fortraders-live-copy" className="text-xs">
          Arm live copy
        </Label>
        <Switch
          id="fortraders-live-copy"
          checked={armed}
          disabled={!canArm && !armed}
          onCheckedChange={(value) => onToggle(Boolean(value))}
        />
      </div>

      <p className="text-xs text-muted-foreground">{hint}</p>
    </section>
  );
}
