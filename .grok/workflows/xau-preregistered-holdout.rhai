let meta = #{
    name: "xau-preregistered-holdout",
    description: "Pre-register ≤6 configs per family, lock 2026 holdout, evaluate once — Fib/Donchian/vol-gate/trail trend — no grids, no live",
    phases: [
        #{ title: "Preregister", detail: "Lock holdout + write frozen config registry" },
        #{ title: "Implement", detail: "Build evaluator for sparse designs on XAU H1" },
        #{ title: "Evaluate", detail: "Run once: train diagnostics + sealed holdout hard gates" },
        #{ title: "Skeptic", detail: "Verify no peek, no extra search, hard gates only" },
        #{ title: "Report", detail: "Survive list or NO-GO + next steps" },
    ],
    when_to_use: "After open multi-design search NO-GO; need honest locked-holdout protocol",
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

phase("Preregister");
log("Lock holdout and pre-register sparse configs (no searching yet)");
let prereg = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "SAFETY: offline only. Never --live. Never open a large grid.\n"
        + "Read: results/xau_new_design_summary.md, results/xau_regime_analysis.json, scripts/xau_new_design_search.py, scripts/htf_fib_offline_backtest.py\n\n"
        + "Write results/xau_preregistered_registry.json with this EXACT protocol:\n"
        + "{\n"
        + "  protocol: {\n"
        + "    holdout_start: '2026-01-01T00:00:00+00:00',\n"
        + "    holdout_rule: 'NEVER used for selection; single evaluation after all configs frozen',\n"
        + "    develop_end: '2025-12-31T23:59:59+00:00',\n"
        + "    max_configs_per_family: 6,\n"
        + "    hard_gates: {profit_factor: 1.5, win_rate: 55.0, max_drawdown_pct: 10.0, n_trades: 20},\n"
        + "    holdout_soft_note: 'if holdout n_trades < 20 report as UNDERPOWERED not pass',\n"
        + "    primary_metric_window: 'holdout only for promotion; develop/train is diagnostic'\n"
        + "  },\n"
        + "  families: [ ... ]\n"
        + "}\n\n"
        + "Pre-register EXACTLY these families with ≤6 frozen configs each (hand-chosen defaults from literature/prior research, NOT from scanning holdout):\n"
        + "1. vol_gate_sparse — single-ish vol-gated BB reclaim; configs vary only atr_max_pct in {0.35,0.40,0.50}, rsi_buy 30/35, sl/tp fixed 1.5/2.5, bb_lo15, ema200, cooldown=2\n"
        + "2. donchian_turtle — entry_N in {20,55}, exit_N in {10,20}, atr_sl 2.0/2.5, atr_tp null (trail: exit on exit_channel break), optional atr_min_pct 0.5, long_only, trend ema200 filter on/off (keep total ≤6)\n"
        + "3. htf_fib_xau — adapt HTF Fib offline logic to XAU H1 CSV; ≤6 configs: with/without RSI SMA filter, sl_atr 1.5/2.0, tp_atr 2.0/3.0, require_ema200_bias true, flat_only\n"
        + "4. atr_trail_breakout — donch breakout entry_N=20/24, atr_min_pct 0.55/0.65, trail_atr 2.5/3.0 (stop trails by ATR), no fixed wide TP; ≤6 configs\n\n"
        + "Each config: {id, family, params, rationale}. Total configs ≤24.\n"
        + "Also write results/xau_holdout_lock.json documenting holdout_start, data_max_time from xauusd_data.csv, and a hash/fingerprint of the registry file content.\n"
        + "Return ok=true if both JSON files written. summary = config counts per family + holdout_start.",
    #{
        label: "preregister-lock",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("Implement");
log("Implement sealed evaluator for pre-registered configs");
let impl = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "SAFETY: offline only. No --live. Do not invent extra configs beyond the registry.\n"
        + "Write scripts/xau_preregistered_holdout.py that:\n"
        + "1. Loads results/xau_preregistered_registry.json (fail if missing)\n"
        + "2. Loads H1 via backtest.load_h1 + indicators; extend with atr_pctile, donchian columns as in xau_new_design_search.py\n"
        + "3. Splits develop (time < holdout_start) vs holdout (time >= holdout_start) using protocol.holdout_start\n"
        + "4. Implements simulators for all 4 families:\n"
        + "   - vol_gate_bb style (reuse simulate_design from xau_new_design_search if importable)\n"
        + "   - donchian turtle: enter long on close > prior donch_hi(entry_N); exit on close < prior donch_lo(exit_N) OR ATR stop; optional ema200 filter; risk 1%\n"
        + "   - htf_fib: port core of scripts/htf_fib_offline_backtest.py onto XAU H1 (H4 pivots from H1 aggregate); risk-sized lots like backtest\n"
        + "   - atr_trail_breakout: enter on breakout; initial SL = entry - trail_atr*ATR; trail stop up on favorable closes; no fixed TP\n"
        + "5. For EACH pre-registered config ONLY (no grid expansion):\n"
        + "   - metrics on develop (diagnostic)\n"
        + "   - metrics on holdout (promotion window)\n"
        + "6. hard_pass_holdout = holds protocol hard_gates on holdout; underpowered if n < 20\n"
        + "7. Write results/xau_preregistered_holdout_eval.json\n"
        + "8. Run: python3 scripts/xau_preregistered_holdout.py  (fix bugs until JSON written)\n"
        + "Do NOT read holdout results and re-pick configs. Single pass.\n"
        + "Return ok=true if eval JSON exists with all configs scored. summary = how many hard_pass / underpowered / fail.",
    #{
        label: "implement-eval",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("Evaluate");
log("Confirm single-pass eval integrity and rank holdout results");
let evaluate = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "Read results/xau_preregistered_holdout_eval.json and results/xau_preregistered_registry.json\n"
        + "Verify:\n"
        + "1. Number of evaluated configs == number registered (no extra trials)\n"
        + "2. holdout_start matches lock\n"
        + "3. Build a clean ranking table by holdout PF among configs with n_trades>=10\n"
        + "4. Write results/xau_preregistered_survivors.json:\n"
        + "   survivors = configs with hard_pass_holdout true\n"
        + "   underpowered_positive = holdout PF>1.2, NP>0, n in [8,19], DD<10 (flag only, not promote)\n"
        + "   if survivors non-empty, also write results/xau_candidate_params.json from the single best survivor by holdout net_profit among hard passers\n"
        + "   if none, survivors=[] and reason string\n"
        + "5. Do NOT re-run search. You may re-run the evaluator once only if the JSON is corrupt/missing fields.\n"
        + "Return ok=true if survivors JSON written. summary = survivor ids or NONE.",
    #{
        label: "rank-survivors",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("Skeptic");
log("Hostile review of preregistered protocol");
let skeptic = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "Hostile quant review. Read registry, lock, eval JSON, survivors, scripts/xau_preregistered_holdout.py\n"
        + "Write results/xau_preregistered_skeptic.md:\n"
        + "1. Was holdout sealed? Any evidence of iterative re-tuning after seeing holdout?\n"
        + "2. Config count vs max 6/family — any hidden search?\n"
        + "3. Look-ahead in Fib pivots (right bars confirmation delay?), Donchian, trails\n"
        + "4. Sample size on holdout per survivor\n"
        + "5. survive count with real=true only if hard gates + clean protocol\n"
        + "6. Explicit promote / do-not-promote\n"
        + "Fail closed. Return ok=true if md written. summary = survive count + promote yes/no.",
    #{
        label: "skeptic",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("Report");
let p_ok = prereg != () && prereg.success && prereg.output != () && prereg.output.ok == true;
let i_ok = impl != () && impl.success && impl.output != () && impl.output.ok == true;
let e_ok = evaluate != () && evaluate.success && evaluate.output != () && evaluate.output.ok == true;
let s_ok = skeptic != () && skeptic.success && skeptic.output != () && skeptic.output.ok == true;

fn sum_of(r) {
    if r != () && r.success && r.output != () && r.output.summary != () {
        return r.output.summary;
    }
    return "n/a";
}

let report = agent(
    "Write results/xau_preregistered_summary.md in /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "SAFETY: never recommend --live. Paper/dry only if skeptic real survivors exist.\n"
        + "Read: xau_preregistered_registry.json, xau_holdout_lock.json, xau_preregistered_holdout_eval.json, xau_preregistered_survivors.json, xau_preregistered_skeptic.md\n"
        + "Numbers only from files.\n"
        + "Phases: PREREG=" + p_ok.to_string() + " " + json_encode(sum_of(prereg))
        + " IMPL=" + i_ok.to_string() + " " + json_encode(sum_of(impl))
        + " EVAL=" + e_ok.to_string() + " " + json_encode(sum_of(evaluate))
        + " SKEPTIC=" + s_ok.to_string() + " " + json_encode(sum_of(skeptic)) + "\n"
        + "Structure: Safety, Protocol, Configs evaluated table (develop vs holdout), Survivors, Skeptic, Winner or NO-GO, Next steps.\n"
        + "Return ok=true if written. summary = one-line winner id or NO-GO.",
    #{
        label: "report",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

let r_ok = report != () && report.success && report.output != () && report.output.ok == true;
let r_sum = "report failed";
if report != () && report.success && report.output != () && report.output.summary != () {
    r_sum = report.output.summary;
}

let all_ok = p_ok && i_ok && e_ok && s_ok && r_ok;
let scratch = "# XAU preregistered holdout\n\n"
    + "- prereg_ok: " + p_ok.to_string() + " — " + sum_of(prereg) + "\n"
    + "- impl_ok: " + i_ok.to_string() + " — " + sum_of(impl) + "\n"
    + "- eval_ok: " + e_ok.to_string() + " — " + sum_of(evaluate) + "\n"
    + "- skeptic_ok: " + s_ok.to_string() + " — " + sum_of(skeptic) + "\n"
    + "- report_ok: " + r_ok.to_string() + " — " + r_sum + "\n"
    + "- all_ok: " + all_ok.to_string() + "\n"
    + "- safety: no --live; holdout sealed\n";

let path = write_scratch_file("xau_preregistered_holdout.md", scratch);
log(scratch);

complete(#{
    summary: r_sum,
    all_ok: all_ok,
    prereg_ok: p_ok,
    impl_ok: i_ok,
    eval_ok: e_ok,
    skeptic_ok: s_ok,
    report_ok: r_ok,
    scratch: path,
    report_path: "results/xau_preregistered_summary.md",
});
