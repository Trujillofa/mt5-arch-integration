"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useDesk } from "@/lib/desk-context";
import { WSF_LIVE_CONFIRM } from "@/lib/wsf/constants";

export function WsfLiveCopy() {
  const { state, setWsfLiveCopy } = useDesk();
  const [ack, setAck] = useState(false);
  const [confirm, setConfirm] = useState("");

  const armed = state.wsfLiveCopy;
  const canArm = ack && confirm === WSF_LIVE_CONFIRM;
  const hint = useMemo(() => {
    if (armed) {
      return "Armed. The next master fill copies to WSF 149736 as a min-lot EURUSDc open (not a scratch). Other slaves stay paper.";
    }
    if (!ack) return "Tick the acknowledgement. This is a real WSF order on each master fill.";
    if (confirm !== WSF_LIVE_CONFIRM) return `Type ${WSF_LIVE_CONFIRM} exactly.`;
    return "Enable the switch to arm live copy.";
  }, [armed, ack, confirm]);

  function onToggle(value: boolean) {
    if (!value) {
      setWsfLiveCopy(false, "");
      setAck(false);
      setConfirm("");
      return;
    }
    const error = setWsfLiveCopy(true, confirm);
    if (error) {
      toast.error(error);
    }
  }

  return (
    <section className="space-y-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
      <div>
        <p className="text-[11px] font-medium tracking-wide text-amber-100 uppercase">
          WSF live copy
        </p>
        <p className="text-xs text-muted-foreground">
          When armed, Place master trade sends the WSF slave fill through{" "}
          <span className="font-mono">POST /api/wsf/order</span> (open, min lot,
          login 149736 only). Paper copy still fans out to the other books.
          Starts the WSF terminal in the background if it is down.
        </p>
      </div>

      <label className="flex items-start gap-2 text-xs text-amber-100/90">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={ack}
          onChange={(event) => {
            setAck(event.target.checked);
            if (!event.target.checked && armed) {
              setWsfLiveCopy(false, "");
            }
          }}
        />
        <span>
          Copy each master fill to live WSF 149736 at 0.01 lot. Not FundedNext,
          not FTMO, not Vantage.
        </span>
      </label>

      <div className="space-y-1.5">
        <Label htmlFor="wsf-copy-confirm">Confirm token</Label>
        <Input
          id="wsf-copy-confirm"
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
          placeholder={WSF_LIVE_CONFIRM}
          autoComplete="off"
          spellCheck={false}
          className="font-mono"
          disabled={armed}
        />
      </div>

      <div className="flex items-center justify-between gap-3">
        <Label htmlFor="wsf-live-copy" className="text-xs">
          Arm live copy
        </Label>
        <Switch
          id="wsf-live-copy"
          checked={armed}
          disabled={!canArm && !armed}
          onCheckedChange={(value) => onToggle(Boolean(value))}
        />
      </div>

      <p className="text-xs text-muted-foreground">{hint}</p>
    </section>
  );
}
