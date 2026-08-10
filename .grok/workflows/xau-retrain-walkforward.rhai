let meta = #{
    name: "xau-retrain-walkforward",
    description: "Next steps after OOS fail: regime IS vs OOS, retrain on train-only, walk-forward — no live",
    phases: [
        #{ title: "Regime", detail: "Compare train vs OOS feature/trade distributions" },
        #{ title: "Retrain", detail: "Param search only on train split; freeze OOS" },
        #{ title: "WalkForward", detail: "Expanding/rolling OOS folds with frozen params" },
        #{ title: "Report", detail: "Write verdict and next actions" },
    ],
    when_to_use: "After fixed-param OOS fails gates; investigate and retrain without peeking at OOS",
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

phase("Regime");
log("Regime analysis: train vs OOS distributions (no live)");
let regime = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "SAFETY: no --live, no order placement.\n"
        + "Write and run a Python script that:\n"
        + "1. Loads H1 via backtest.load_h1 + indicators\n"
        + "2. Split at 70% time (same as results/xau_oos_holdout.json if present)\n"
        + "3. Compares train vs OOS: bar count, mean/std of close returns, ATR, RSI, bb width, fraction close>ema200\n"
        + "4. With FIXED params from strategy_params.json, run simulate on each segment and print metrics\n"
        + "5. Monthly trade proxy: count long signal bars per month train vs OOS (reuse simulate logic or bar conditions)\n"
        + "6. Write JSON to results/xau_regime_analysis.json\n"
        + "Return ok=true if JSON written. summary = 1-2 sentences on whether regime shifted. details = key numbers.",
    #{
        label: "regime-analysis",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("Retrain");
log("Param search ONLY on train split; never fit on OOS");
let retrain = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "SAFETY: no --live. Do NOT overwrite strategy_params.json unless train-only candidate beats current on train AND you write a separate file first.\n"
        + "Write/run Python that:\n"
        + "1. load_h1 + indicators; 70% time split → train only for search\n"
        + "2. Grid-search a compact space (keep it under ~2 minutes):\n"
        + "   rsi_buy in (25,30,35); rsi_sell in (50,55,60); sl_atr/tp_atr in ((1.0,1.5),(1.5,2.0),(1.2,2.5));\n"
        + "   require_uptrend in (True,False); bb_col in ('bb_lo','bb_lo15'); cooldown in (1,2,3);\n"
        + "   mode=bb_rsi, long_only=True, risk_pct=0.01, trend_col=ema200, use_macd_filter=False\n"
        + "3. Score with backtest.passes then highest net_profit among passers; else best PF among PF>1.0\n"
        + "4. Evaluate winner on frozen OOS once (report only — do not re-search OOS)\n"
        + "5. Also evaluate current strategy_params.json on train and OOS for comparison\n"
        + "6. Write results/xau_train_only_retrain.json with: best_params, train_metrics, oos_metrics, baseline_train, baseline_oos, oos_gates_pass, search_size\n"
        + "7. Optionally write results/xau_candidate_params.json (candidate only; do not replace strategy_params.json unless oos_gates_pass and n_trades>=15)\n"
        + "Return ok=true if JSON written. summary must include train PF/WR/DD/n and OOS PF/WR/DD/n and whether OOS gates pass.",
    #{
        label: "train-only-retrain",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("WalkForward");
log("Walk-forward folds with train-fit then OOS eval");
let wf = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "SAFETY: no --live. No fitting on test folds.\n"
        + "Write/run Python walk-forward:\n"
        + "1. H1 bars chronological. Use expanding train / fixed OOS folds OR 3–4 sequential folds:\n"
        + "   Example: fold k trains on data before fold start, tests next ~90–120 calendar days (or equal bar chunks).\n"
        + "   Aim for 3+ OOS folds covering 2025–2026 if data allows.\n"
        + "2. Per fold: small grid on TRAIN only (subset of retrain grid if slow — e.g. rsi_buy 25/30/35, sl/tp (1.0,1.5)/(1.5,2.0), require_uptrend T/F), pick best by passes then net_profit\n"
        + "3. Evaluate chosen params on that fold's OOS only; record metrics + params + bar ranges\n"
        + "4. Aggregate: sum net_profit, total trades, mean WR/PF, fraction folds with passes(oos), min OOS DD\n"
        + "5. Also run a pure forward test using fixed current strategy_params across the same OOS folds (no retrain) for baseline\n"
        + "6. Write results/xau_walkforward.json\n"
        + "Return ok=true if written. summary = aggregate OOS PF-ish stats, fold pass rate, total OOS trades, vs fixed-param baseline.",
    #{
        label: "walk-forward",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("Report");
log("Synthesize regime + retrain + walk-forward");
let r_ok = regime != () && regime.success && regime.output != () && regime.output.ok == true;
let t_ok = retrain != () && retrain.success && retrain.output != () && retrain.output.ok == true;
let w_ok = wf != () && wf.success && wf.output != () && wf.output.ok == true;

let r_sum = "regime n/a";
if regime != () && regime.success && regime.output != () && regime.output.summary != () {
    r_sum = regime.output.summary;
}
let t_sum = "retrain n/a";
if retrain != () && retrain.success && retrain.output != () && retrain.output.summary != () {
    t_sum = retrain.output.summary;
}
let w_sum = "wf n/a";
if wf != () && wf.success && wf.output != () && wf.output.summary != () {
    w_sum = wf.output.summary;
}
let r_det = "";
if regime != () && regime.success && regime.output != () && regime.output.details != () {
    r_det = regime.output.details;
}
let t_det = "";
if retrain != () && retrain.success && retrain.output != () && retrain.output.details != () {
    t_det = retrain.output.details;
}
let w_det = "";
if wf != () && wf.success && wf.output != () && wf.output.details != () {
    w_det = wf.output.details;
}

let report = agent(
    "Write markdown report to /home/yderf/Projects/trading/mt5-arch-integration/results/xau_retrain_walkforward_summary.md\n"
        + "SAFETY note: no live trading recommended unless evidence clearly supports it.\n"
        + "Read any of: results/xau_regime_analysis.json, results/xau_train_only_retrain.json, results/xau_walkforward.json, results/xau_oos_holdout.json\n"
        + "Use ONLY numbers from those files / phase payloads — do not invent.\n\n"
        + "Phase payloads:\n"
        + "REGIME_OK=" + r_ok.to_string() + " SUMMARY=" + json_encode(r_sum) + " DETAILS=" + json_encode(r_det) + "\n"
        + "RETRAIN_OK=" + t_ok.to_string() + " SUMMARY=" + json_encode(t_sum) + " DETAILS=" + json_encode(t_det) + "\n"
        + "WF_OK=" + w_ok.to_string() + " SUMMARY=" + json_encode(w_sum) + " DETAILS=" + json_encode(w_det) + "\n\n"
        + "Structure:\n"
        + "# XAU retrain + walk-forward\n"
        + "## Safety (no live)\n"
        + "## Regime shift findings\n"
        + "## Train-only retrain vs baseline\n"
        + "## Walk-forward aggregate\n"
        + "## Go / no-go gates\n"
        + "## Recommended next steps (ordered)\n\n"
        + "Decision rules for Recommended next steps:\n"
        + "- If retrain OOS still fails and WF fold pass rate < 50% or total OOS trades thin: stay dry-only, consider strategy redesign or HTF Fib path, not param thrashing.\n"
        + "- If retrain OOS passes with n_trades>=15 AND WF mostly positive: still no live; next is paper/dry loop monitoring + MT5 Python bridge for real dry order path.\n"
        + "- Never recommend --live in this report.\n"
        + "Return ok=true if file written. summary = path + one-line go/no-go.",
    #{
        label: "write-report",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

let rep_ok = report != () && report.success && report.output != () && report.output.ok == true;
let rep_sum = "report failed";
if report != () && report.success && report.output != () && report.output.summary != () {
    rep_sum = report.output.summary;
}

let all_ok = r_ok && t_ok && w_ok && rep_ok;
let scratch = "# XAU retrain + walk-forward\n\n"
    + "- regime_ok: " + r_ok.to_string() + " — " + r_sum + "\n"
    + "- retrain_ok: " + t_ok.to_string() + " — " + t_sum + "\n"
    + "- walkforward_ok: " + w_ok.to_string() + " — " + w_sum + "\n"
    + "- report_ok: " + rep_ok.to_string() + " — " + rep_sum + "\n"
    + "- all_ok: " + all_ok.to_string() + "\n"
    + "- artifacts: results/xau_regime_analysis.json, results/xau_train_only_retrain.json, results/xau_walkforward.json, results/xau_retrain_walkforward_summary.md\n"
    + "- safety: never --live\n";

let path = write_scratch_file("xau_retrain_walkforward.md", scratch);
log(scratch);

complete(#{
    summary: rep_sum,
    all_ok: all_ok,
    regime_ok: r_ok,
    retrain_ok: t_ok,
    walkforward_ok: w_ok,
    report_ok: rep_ok,
    scratch: path,
    report_path: "results/xau_retrain_walkforward_summary.md",
});
