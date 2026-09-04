"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useDesk } from "@/lib/desk-context";
import { FUNDINGPIPS_LIVE_CONFIRM } from "@/lib/fundingpips/types";

export function FundingPipsLiveCopy() {
  const { state, setFundingpipsLiveCopy } = useDesk();
  const [ack, setAck] = useState(false);
  const [confirm, setConfirm] = useState("");

  const armed = state.fundingpipsLiveCopy;
  const canArm = ack && confirm === FUNDINGPIPS_LIVE_CONFIRM;
  const hint = useMemo(() => {
    if (armed) {
      return "Armed. Each master fill copies to FundingPips 11669306 as 0.01 EURUSD.";
    }
    if (!ack) return "Tick the acknowledgement. This is a real FundingPips order on each master fill.";
    if (confirm !== FUNDINGPIPS_LIVE_CONFIRM) return `Type ${FUNDINGPIPS_LIVE_CONFIRM} exactly.`;
    return "Enable the switch to arm live copy.";
  }, [armed, ack, confirm]);

  function onToggle(value: boolean) {
    if (!value) {
      setFundingpipsLiveCopy(false, "");
      setAck(false);
      setConfirm("");
      return;
    }
    const error = setFundingpipsLiveCopy(true, confirm);
    if (error) toast.error(error);
  }

  return (
    <section className="space-y-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
      <div>
        <p className="text-[11px] font-medium tracking-wide text-amber-100 uppercase">
          FundingPips live copy
        </p>
        <p className="text-xs text-muted-foreground">
          When armed, Place master trade sends the FundingPips slave through{" "}
          <span className="font-mono">POST /api/fundingpips/order</span> (open, min
          lot, login 11669306). Other non-armed slaves stay paper. Not FP Markets.
        </p>
      </div>

      <label className="flex items-start gap-2 text-xs text-amber-100/90">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={ack}
          onChange={(event) => {
            setAck(event.target.checked);
            if (!event.target.checked && armed) setFundingpipsLiveCopy(false, "");
          }}
        />
        <span>
          Copy each master fill to live FundingPips 11669306 at 0.01 lot. Not
          Vantage, not FP Markets.
        </span>
      </label>

      <div className="space-y-1.5">
        <Label htmlFor="fundingpips-copy-confirm">Confirm token</Label>
        <Input
          id="fundingpips-copy-confirm"
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
          placeholder={FUNDINGPIPS_LIVE_CONFIRM}
          autoComplete="off"
          spellCheck={false}
          className="font-mono"
          disabled={armed}
        />
      </div>

      <div className="flex items-center justify-between gap-3">
        <Label htmlFor="fundingpips-live-copy" className="text-xs">
          Arm live copy
        </Label>
        <Switch
          id="fundingpips-live-copy"
          checked={armed}
          disabled={!canArm && !armed}
          onCheckedChange={(value) => onToggle(Boolean(value))}
        />
      </div>

      <p className="text-xs text-muted-foreground">{hint}</p>
    </section>
  );
}
