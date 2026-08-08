let meta = #{
    name: "xau-post-kill-continue",
    description: "After KILL_BB_RSI_LINE: wire costs into lane sims, re-eval frozen champions, update disposition",
    phases: [
        #{ title: "Map", detail: "Where lane sims ignore spread; remaining research lanes" },
        #{ title: "Wire-costs", detail: "Charge strategy_params costs in lane simulators" },
        #{ title: "Re-eval", detail: "Frozen multi-year catalog under measured costs" },
        #{ title: "Skeptic", detail: "Hostile read of costed multi-year + next_step" },
        #{ title: "Status", detail: "Update xau_loop_status.md and write summary" },
    ],
    when_to_use: "After null max-stat kills bb_rsi; continue with costed non-bb_rsi lanes only",
};

let result_schema = #{
    "type": "object",
    "required": ["ok", "summary", "details"],
    "properties": #{
        "ok": #{ "type": "boolean" },
        "summary": #{ "type": "string" },
        "details": #{ "type": "string" },
    },
};

let root = "/home/yderf/Projects/trading/mt5-arch-integration";

// ---------------------------------------------------------------------------
phase("Map");
log("Map cost gaps and surviving lanes after bb_rsi kill");

let map_prompt = "";
map_prompt += "Repo: " + root + "\n";
map_prompt += "SAFETY: offline only. NEVER --live. NEVER place orders. Holdout sealed for selection.\n\n";
map_prompt += "Context (already done — do not re-run bb_rsi search):\n";
map_prompt += "- results/xau_null_maxstat.md disposition KILL_BB_RSI_LINE (p_max_pf=0.854, p_n_passers=0.707)\n";
map_prompt += "- results/xau_loop_status.md records the kill; measured spread is in xauusd_data.csv\n";
map_prompt += "- strategy_params.json costs: spread_col=spread, commission=0, slippage=0\n";
map_prompt += "- backtest.simulate() charges costs; lane sims in scripts/xau_lane_deep_opt.py likely do NOT\n\n";
map_prompt += "Tasks (read-only tools first: read_file, grep, list_dir):\n";
map_prompt += "1. Read results/xau_loop_status.md, results/xau_null_maxstat.md, results/xau_frozen_champions_catalog.json\n";
map_prompt += "2. Grep scripts/xau_lane_deep_opt.py and scripts/xau_frozen_multi_year_eval.py for spread/commission/trade_cost\n";
map_prompt += "3. Confirm which of simulate_donchian / atr_trail / htf_fib / vol_gate / htf_pullback charge costs\n";
map_prompt += "4. List frozen catalog lanes still worth costed re-eval (exclude bb_rsi search family)\n";
map_prompt += "5. Write a short plan to results/xau_post_kill_plan.md: gaps, exact files to edit, re-eval command, success criteria\n\n";
map_prompt += "Return ok=true only if the plan file exists. summary = one sentence on the biggest cost gap.";

let map_r = agent(
    map_prompt,
    #{
        label: "map-cost-gaps",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

if map_r == () || !map_r.success {
    complete(#{
        ok: false,
        summary: "Map phase failed; abort before code changes",
        details: "map agent did not succeed",
    });
}

// ---------------------------------------------------------------------------
phase("Wire-costs");
log("Wire measured costs into lane simulators used by frozen multi-year");

let wire_prompt = "";
wire_prompt += "Repo: " + root + "\n";
wire_prompt += "SAFETY: offline only. NEVER --live. Do not overwrite strategy_params.json.\n";
wire_prompt += "Do not resurrect bb_rsi search tuning.\n\n";
wire_prompt += "Read results/xau_post_kill_plan.md and implement cost charging in lane simulators.\n\n";
wire_prompt += "Requirements:\n";
wire_prompt += "1. Load costs from strategy_params.json costs block (spread_col, point_size, commission_per_lot, slippage_points)\n";
wire_prompt += "   the same way scripts/xau_walkforward.py wraps backtest.simulate.\n";
wire_prompt += "2. In scripts/xau_lane_deep_opt.py, charge round-trip cost on every closed trade for:\n";
wire_prompt += "   simulate_donchian, simulate_atr_trail, simulate_htf_fib_enhanced, simulate_vol_gate, simulate_htf_pullback\n";
wire_prompt += "   Formula should match backtest.simulate: (spread_pts + 2*slippage_points)*point_size*CONTRACT_SIZE*lots + 2*commission_per_lot*lots\n";
wire_prompt += "   priced off the entry bar. Accept spread_col / point_size / commission_per_lot / slippage_points kwargs with defaults 0/None so frictionless still works.\n";
wire_prompt += "3. scripts/xau_frozen_multi_year_eval.py must pass saved costs into every sim call (or set a module-level COSTS default).\n";
wire_prompt += "4. Zero-spread bars are already median-filled in the CSV; do not re-invent that.\n";
wire_prompt += "5. Keep partial-TP legs costed reasonably (at least charge full RT once per entry, same as backtest pattern).\n";
wire_prompt += "6. Run a quick smoke: import the module, sim one frozen donchian config on a small develop slice with and without spread; print both NPs.\n";
wire_prompt += "7. uv run pytest tests/test_xau_pipeline.py -q  (must still pass; do not break backtest path)\n\n";
wire_prompt += "Return ok=true if costs are wired and smoke shows lower NP with spread. summary = files changed + smoke delta.";

let wire_r = agent(
    wire_prompt,
    #{
        label: "wire-lane-costs",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

if wire_r == () || !wire_r.success || wire_r.output.ok != true {
    let det = "wire phase failed";
    if wire_r != () && wire_r.success && wire_r.output.details != () {
        det = wire_r.output.details;
    }
    complete(#{
        ok: false,
        summary: "Cost wiring failed; skip re-eval",
        details: det,
    });
}

// ---------------------------------------------------------------------------
phase("Re-eval");
log("Re-run frozen multi-year catalog under measured costs");

let eval_prompt = "";
eval_prompt += "Repo: " + root + "\n";
eval_prompt += "SAFETY: offline only. NEVER retune. NEVER --live. Params ONLY from results/xau_frozen_champions_catalog.json\n\n";
eval_prompt += "Re-run the frozen multi-year evaluation WITH costs now wired:\n";
eval_prompt += "1. python3 scripts/xau_frozen_multi_year_eval.py  (or the module's CLI) until it completes\n";
eval_prompt += "2. Ensure outputs overwrite/update:\n";
eval_prompt += "   results/xau_frozen_multi_year_eval.json\n";
eval_prompt += "   results/xau_frozen_multi_year_matrix.csv\n";
eval_prompt += "3. Embed or record the costs block used in the JSON so future readers know it was costed\n";
eval_prompt += "4. Print compact table: per lane, develop_like and year windows PF/NP/n/hard_pass\n";
eval_prompt += "5. Compare roughly to prior frictionless story (Donchian was sign-stable; ATR collapsed 2023) — note what changed under spread\n\n";
eval_prompt += "If the script is too slow, still finish the full catalog (8 configs) — do not subsample.\n";
eval_prompt += "Return ok=true if JSON+CSV written with costs. summary = hard_pass cell count and which lanes still sign-stable.";

let eval_r = agent(
    eval_prompt,
    #{
        label: "costed-multi-year",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

// ---------------------------------------------------------------------------
phase("Skeptic");
log("Hostile skeptic on costed multi-year; do not promote");

let sk_prompt = "";
sk_prompt += "Repo: " + root + "\n";
sk_prompt += "SAFETY: offline. promote=no unless extraordinary evidence (there will not be any).\n\n";
sk_prompt += "Read:\n";
sk_prompt += "- results/xau_frozen_multi_year_eval.json (costed re-run)\n";
sk_prompt += "- results/xau_frozen_multi_year_matrix.csv\n";
sk_prompt += "- results/xau_null_maxstat.md (bb_rsi is DEAD — do not revive)\n";
sk_prompt += "- results/xau_frozen_multi_year_skeptic.md (prior frictionless skeptic)\n\n";
sk_prompt += "Write results/xau_frozen_multi_year_costed_skeptic.md with:\n";
sk_prompt += "1. Which lanes remain sign-stable after spread\n";
sk_prompt += "2. Which lanes die under costs\n";
sk_prompt += "3. Explicit promote=no / live_go=false\n";
sk_prompt += "4. next_step: only if a lane is still interesting, propose ONE decisive offline test (e.g. Donchian null max-stat); else RESEARCH_IDLE\n";
sk_prompt += "5. List open housekeeping (charter PR, CSV history, Exness symbols, ruff) as non-research\n\n";
sk_prompt += "Return ok=true if skeptic file written. summary = next_step one-liner.";

let sk_r = agent(
    sk_prompt,
    #{
        label: "costed-skeptic",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

// ---------------------------------------------------------------------------
phase("Status");
log("Update loop status and synthesis report");

let st_prompt = "";
st_prompt += "Repo: " + root + "\n";
st_prompt += "Prepend a new dated section to results/xau_loop_status.md for this fire:\n";
st_prompt += "- title: costed frozen multi-year after bb_rsi kill\n";
st_prompt += "- costs used\n";
st_prompt += "- hard_pass counts if available\n";
st_prompt += "- live_go=false, promote=no\n";
st_prompt += "- next_step from the skeptic\n";
st_prompt += "- link artifacts: plan, costed skeptic, multi-year json/csv\n\n";
st_prompt += "Also write results/xau_post_kill_summary.md: executive summary of kill + costed re-eval + what to do next (research vs housekeeping).\n";
st_prompt += "If there are uncommitted code changes from wire/re-eval, leave them uncommitted (parent will commit); list files changed via git status.\n\n";
st_prompt += "Return ok=true if status + summary written. summary = disposition + next_step.";

let st_r = agent(
    st_prompt,
    #{
        label: "update-status",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

// ---------------------------------------------------------------------------
let map_ok = map_r != () && map_r.success && map_r.output.ok == true;
let wire_ok = wire_r != () && wire_r.success && wire_r.output.ok == true;
let eval_ok = eval_r != () && eval_r.success && eval_r.output.ok == true;
let sk_ok = sk_r != () && sk_r.success && sk_r.output.ok == true;
let st_ok = st_r != () && st_r.success && st_r.output.ok == true;

let all_ok = map_ok && wire_ok && eval_ok && sk_ok && st_ok;

let summary = "post-kill continue: ";
if all_ok {
    summary += "OK — costed multi-year + skeptic + status written";
} else {
    summary += "PARTIAL — check phase flags";
}

let details = "";
details += "map=" + map_ok.to_string();
details += " wire=" + wire_ok.to_string();
details += " eval=" + eval_ok.to_string();
details += " skeptic=" + sk_ok.to_string();
details += " status=" + st_ok.to_string();
if st_r != () && st_r.success && st_r.output.summary != () {
    details += " | " + st_r.output.summary;
}

complete(#{
    ok: all_ok,
    summary: summary,
    details: details,
});
