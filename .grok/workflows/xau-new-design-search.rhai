let meta = #{
    name: "xau-new-design-search",
    description: "Find new profitable XAU H1 designs after bb_rsi OOS fail: invent, implement, train-only search, OOS+WF validate, skeptic — no live",
    phases: [
        #{ title: "Design", detail: "Propose regime-aware strategy families from evidence" },
        #{ title: "BuildSearch", detail: "Implement multi-design simulator + train-only search" },
        #{ title: "Validate", detail: "Holdout OOS + walk-forward on shortlist" },
        #{ title: "Skeptic", detail: "Adversarial check for overfit / leakage" },
        #{ title: "Report", detail: "Ranked designs and go/no-go" },
    ],
    when_to_use: "After bb_rsi regime failure; need new strategy families not param thrash",
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

phase("Design");
log("Propose new designs from regime evidence (no live)");
let design = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "SAFETY: offline research only. Never --live. Never place orders.\n"
        + "Read evidence files with tools:\n"
        + "- results/xau_regime_analysis.json\n"
        + "- results/xau_retrain_walkforward_summary.md\n"
        + "- results/xau_oos_holdout.json\n"
        + "- backtest.py (simulate modes, passes gates)\n"
        + "- scripts/htf_fib_offline_backtest.py (skim for alternate thesis)\n\n"
        + "Write results/xau_new_design_specs.json with 4–6 DISTINCT strategy families that address the 2026 regime shift (ATR ~2.4×, lower frac>EMA200, mean-reversion failure).\n"
        + "Each family object must include:\n"
        + "  id, name, thesis (why it should work in high-vol and/or dual regime),\n"
        + "  entry_rules (precise, implementable on H1 OHLC+indicators),\n"
        + "  exit_rules (SL/TP in ATR multiples and/or soft exits),\n"
        + "  filters (vol percentile, trend, session optional),\n"
        + "  param_grid (small discrete ranges),\n"
        + "  invalidation (when not to trade).\n\n"
        + "Required families to include (you may refine names/params):\n"
        + "1. vol_gate_meanrev — only trade bb-style mean reversion when atr_pctile is LOW/MED (train-like)\n"
        + "2. atr_breakout_trend — trade WITH high vol: N-bar high breakout + EMA trend, wider stops\n"
        + "3. ema_pullback_trend — strong uptrend pullback to ema20/50 with RSI not extreme; optional atr_pctile mid\n"
        + "4. dual_regime_switch — if atr_pctile high → breakout mode else meanrev mode\n"
        + "5. optional: htf_fib_proxy or donchian_channel if easy to specify from existing code\n\n"
        + "Gates to target later: PF>1.5, WR>55%, MaxDD<10%, n_trades>=20 on train; OOS n>=10 preferred.\n"
        + "Return ok=true if JSON written. summary = list of family ids. details = brief theses.",
    #{
        label: "design-specs",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("BuildSearch");
log("Implement multi-design engine + train-only multi-family search");
let build = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "SAFETY: offline only. No --live. Do not overwrite strategy_params.json.\n"
        + "Implement scripts/xau_new_design_search.py that:\n\n"
        + "1. Imports load_h1, indicators, Metrics, metrics_from_pnls, START_BALANCE, CONTRACT_SIZE, passes from backtest.py\n"
        + "2. Extends indicators with: atr_pctile (rolling 100 rank of atr), donch_hi/lo (N=20/55), ema20 already exists\n"
        + "3. Implements simulate_design(d, **params) supporting modes at least:\n"
        + "   - vol_gate_bb: like bb_rsi long reclaim but ONLY if atr_pctile <= atr_max_pct (e.g. 0.5/0.6/0.7)\n"
        + "   - atr_breakout: long if close > donch_hi[i-1] and close > trend_ema and atr_pctile >= atr_min_pct; SL atr*sl; TP atr*tp or trail optional simple fixed TP\n"
        + "   - ema_pullback: long if close>ema200, low<=ema20 or ema50, close>ema20, rsi between lo/hi, atr_pctile in band\n"
        + "   - dual_regime: if atr_pctile >= switch_pct use atr_breakout rules else vol_gate_bb rules\n"
        + "   Reuse position sizing / min-lot risk skip / cooldown / long_only from backtest.simulate patterns\n"
        + "4. 70% time train split (same as prior OOS split if results/xau_oos_holdout.json exists)\n"
        + "5. Train-only grid per family from results/xau_new_design_specs.json if present, else hardcode compact grids:\n"
        + "   Keep total evals under ~4000 or finish in <3 min. Prioritize coverage over exhaustiveness.\n"
        + "6. Score: prefer passes(train) then net_profit; secondary score if none pass\n"
        + "7. For top 1 per family + global top 3: evaluate frozen OOS once\n"
        + "8. Write results/xau_new_design_search.json with families, all_passers_train count, shortlist[{id,params,train,oos,oos_gates}]\n"
        + "9. Run the script: python3 scripts/xau_new_design_search.py\n"
        + "10. Fix any bugs until JSON is written with real numbers\n\n"
        + "Do NOT fit on OOS. Do NOT claim profitability without OOS metrics in the JSON.\n"
        + "Return ok=true if search JSON written and at least one family evaluated. summary = best train PF/OOS PF per shortlist head.",
    #{
        label: "build-and-search",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("Validate");
log("Walk-forward validate shortlist designs");
let validate = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "SAFETY: offline only. No --live.\n"
        + "Read results/xau_new_design_search.json shortlist.\n"
        + "Write and run scripts/xau_new_design_walkforward.py:\n"
        + "- Reuse simulate_design from xau_new_design_search (import or duplicate carefully)\n"
        + "- Expanding train + 4 equal-bar OOS folds from 2025-01-01 (same spirit as scripts/xau_walkforward.py)\n"
        + "- For each shortlist design (max 5):\n"
        + "  A) Fixed params from shortlist across folds (no re-fit)\n"
        + "  B) Optional light re-fit on train per fold (small neighbor grid) if time allows — mark clearly\n"
        + "- Aggregate per design: sum OOS NP, total trades, mean PF/WR, fold_pass_rate (use passes() or softer oos pass if n<20: PF>1.2 WR>50 DD<12 for fold-level 'soft_pass')\n"
        + "- Write results/xau_new_design_walkforward.json\n"
        + "- Also write results/xau_new_design_candidates.json with any design where:\n"
        + "  train passes gates AND oos PF>1.2 AND oos n>=8 AND (wf fold soft_pass_rate >= 0.5 OR fixed-param sum OOS NP>0 with mean PF>1.2)\n"
        + "  If none qualify, write empty candidates list with reason.\n\n"
        + "Return ok=true if WF JSON written. summary = which designs (if any) survive validation.",
    #{
        label: "validate-wf",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("Skeptic");
log("Adversarial overfit / leakage review");
let skeptic = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "You are a hostile quant reviewer. Read:\n"
        + "- results/xau_new_design_search.json\n"
        + "- results/xau_new_design_walkforward.json\n"
        + "- results/xau_new_design_candidates.json (if any)\n"
        + "- scripts/xau_new_design_search.py (check for look-ahead, train contamination, bug-inflated metrics)\n\n"
        + "Write results/xau_new_design_skeptic.md covering:\n"
        + "1. Look-ahead / leakage risks (e.g. atr_pctile using future, donchian same-bar, split bugs)\n"
        + "2. Multiple testing / overfit risk from grid size\n"
        + "3. Sample size adequacy on OOS\n"
        + "4. Which candidate claims survive scrutiny (real=true only with evidence)\n"
        + "5. Explicit NO-GO if nothing survives\n\n"
        + "Fail closed: if evidence missing, mark unverified.\n"
        + "Return ok=true if skeptic md written. summary = survive count + hard recommendation.",
    #{
        label: "skeptic-review",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("Report");
let d_ok = design != () && design.success && design.output != () && design.output.ok == true;
let b_ok = build != () && build.success && build.output != () && build.output.ok == true;
let v_ok = validate != () && validate.success && validate.output != () && validate.output.ok == true;
let s_ok = skeptic != () && skeptic.success && skeptic.output != () && skeptic.output.ok == true;

fn sum_of(r) {
    if r != () && r.success && r.output != () && r.output.summary != () {
        return r.output.summary;
    }
    return "n/a";
}
fn det_of(r) {
    if r != () && r.success && r.output != () && r.output.details != () {
        return r.output.details;
    }
    return "";
}

let report = agent(
    "Write /home/yderf/Projects/trading/mt5-arch-integration/results/xau_new_design_summary.md\n"
        + "SAFETY: never recommend --live. Paper/dry only if candidates survive skeptic.\n"
        + "Read all of: xau_new_design_specs.json, xau_new_design_search.json, xau_new_design_walkforward.json, xau_new_design_candidates.json, xau_new_design_skeptic.md\n"
        + "Use only real numbers from those files.\n\n"
        + "Phase notes:\n"
        + "DESIGN_OK=" + d_ok.to_string() + " " + json_encode(sum_of(design)) + "\n"
        + "BUILD_OK=" + b_ok.to_string() + " " + json_encode(sum_of(build)) + "\n"
        + "VALIDATE_OK=" + v_ok.to_string() + " " + json_encode(sum_of(validate)) + "\n"
        + "SKEPTIC_OK=" + s_ok.to_string() + " " + json_encode(sum_of(skeptic)) + "\n\n"
        + "Structure:\n"
        + "# XAU new design search\n"
        + "## Safety\n## Designs evaluated\n## Train / OOS table (all shortlist)\n## Walk-forward ranking\n## Skeptic verdict\n## Winner(s) or none\n## Recommended next steps\n\n"
        + "If a design clearly wins with skeptic approval: propose writing results/xau_candidate_params.json and dry-run path — still no live.\n"
        + "If none: recommend concrete redesign directions (not more random grids).\n"
        + "Return ok=true if summary written. summary = one-line winner or NO-GO.",
    #{
        label: "final-report",
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

let all_ok = d_ok && b_ok && v_ok && s_ok && r_ok;
let scratch = "# XAU new design search\n\n"
    + "- design_ok: " + d_ok.to_string() + " — " + sum_of(design) + "\n"
    + "- build_ok: " + b_ok.to_string() + " — " + sum_of(build) + "\n"
    + "- validate_ok: " + v_ok.to_string() + " — " + sum_of(validate) + "\n"
    + "- skeptic_ok: " + s_ok.to_string() + " — " + sum_of(skeptic) + "\n"
    + "- report_ok: " + r_ok.to_string() + " — " + r_sum + "\n"
    + "- all_ok: " + all_ok.to_string() + "\n"
    + "- safety: no --live\n";

let path = write_scratch_file("xau_new_design_search.md", scratch);
log(scratch);

complete(#{
    summary: r_sum,
    all_ok: all_ok,
    design_ok: d_ok,
    build_ok: b_ok,
    validate_ok: v_ok,
    skeptic_ok: s_ok,
    report_ok: r_ok,
    scratch: path,
    report_path: "results/xau_new_design_summary.md",
});
