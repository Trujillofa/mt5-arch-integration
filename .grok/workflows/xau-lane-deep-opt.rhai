let meta = #{
    name: "xau-lane-deep-opt",
    description: "Deep-optimize ALL XAU lanes on develop (X.com ideas + local search); never discard early; sealed holdout once — no live",
    phases: [
        #{ title: "Ingest", detail: "X notes + prior results into opt charter" },
        #{ title: "FixFib", detail: "Fix Fib pivot confirmation; enable fib lane" },
        #{ title: "DeepOpt", detail: "Exhaustive develop-only opt per lane" },
        #{ title: "SealedHoldout", detail: "One frozen holdout eval of champions" },
        #{ title: "Skeptic", detail: "Overfit / leakage / early-discard audit" },
        #{ title: "Report", detail: "Keep/kill per lane with evidence" },
    ],
    when_to_use: "After preregistered NO-GO when user wants max tune before discarding lanes",
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

phase("Ingest");
log("Charter: X.com ideas + no early discard");
let ingest = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "SAFETY: offline only. Never --live.\n"
        + "Read:\n"
        + "- results/xau_xcom_research_notes.md\n"
        + "- results/xau_preregistered_summary.md\n"
        + "- results/xau_preregistered_holdout_eval.json (skim)\n"
        + "- results/xau_regime_analysis.json\n"
        + "- scripts/xau_preregistered_holdout.py\n"
        + "- scripts/xau_new_design_search.py\n\n"
        + "Write results/xau_lane_opt_charter.json:\n"
        + "{\n"
        + "  doctrine: 'never discard lane until develop opt budget exhausted',\n"
        + "  develop_end: '2025-12-31',\n"
        + "  holdout_start: '2026-01-01',\n"
        + "  holdout_sealed_until: 'after_champions_frozen',\n"
        + "  xcom_ideas: [list of implementable rules from the notes],\n"
        + "  lanes: [\n"
        + "    {id, status_prior, keep_reason, develop_objective, search_budget_evals, structure_variants[]},\n"
        + "  for vol_gate_sparse, donchian_turtle, atr_trail_breakout, htf_fib_xau, htf_pullback_new]\n"
        + "  discard_policy: 'only after budget done AND develop still fails soft floor AND holdout not used for tuning'\n"
        + "}\n"
        + "Include NEW lane htf_pullback_new: H4/H1 bias + pullback to ema20/50 + optional session London/NY hours + BE at 1R (from X buy-the-dip theme).\n"
        + "Return ok=true if charter written. summary = lane ids + budgets.",
    #{
        label: "ingest-charter",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("FixFib");
log("Fix Fib confirmation lag so fib lane can be optimized fairly");
let fixfib = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "SAFETY: offline only.\n"
        + "Fix HTF Fib pivot confirmation look-ahead:\n"
        + "1. Read scripts/htf_fib_offline_backtest.py and fib path inside scripts/xau_preregistered_holdout.py\n"
        + "2. Pivot events must become active only at index c+right (confirmation bar), never at pivot center c\n"
        + "3. Prefer implementing fix in a shared helper used by preregistered evaluator and a new optimizer\n"
        + "4. Add a unit-style self-check: for synthetic series, signal time >= pivot_center + right\n"
        + "5. Write results/xau_fib_fix_note.md with before/after description\n"
        + "Do not evaluate holdout here. Return ok=true if fix landed and self-check passes.",
    #{
        label: "fix-fib",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("DeepOpt");
log("Deep develop-only optimization — ALL lanes, no early kill");
let deep = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "SAFETY: offline only. NEVER read holdout metrics to choose params. NEVER --live.\n"
        + "Doctrine: optimize as much as possible BEFORE discarding any lane.\n\n"
        + "Write and run scripts/xau_lane_deep_opt.py:\n\n"
        + "### Data\n"
        + "- load_h1 + indicators + atr_pctile + donchian from existing helpers\n"
        + "- develop = time < 2026-01-01; holdout NOT used in this phase\n"
        + "- Optional develop inner CV: last 20% of develop as 'pseudo-val' for ranking only (still not the sealed 2026 holdout)\n\n"
        + "### Features / X.com rules to implement\n"
        + "- h4_bias: resample H1→H4 EMA200; only long if H4 close > H4 ema200 (or param off)\n"
        + "- max_entries_per_day (1 or 2)\n"
        + "- be_at_r: after unrealized + be_at_r * initial_risk, move SL to entry\n"
        + "- session hours optional (7-17, 12-21 UTC)\n"
        + "- failed_breakout_fade optional for low atr_pctile only\n\n"
        + "### Lanes (ALL must consume full budget; no early discard)\n"
        + "1. vol_gate_sparse — expand atr_max_pct, rsi, bb_col, cooldown, exit_on_vol_spike, h4_bias, hours, be_at_r; objective: train PF/WR/DD + maximize n_trades (target n>=25 on develop)\n"
        + "2. donchian_turtle — entry_N/exit_N, atr_sl, h4_bias, mid_channel_k*ATR filter, be_at_r, partial_tp optional (50% at 1.5R); objective: expectancy*sqrt(n), PF, DD (WR secondary)\n"
        + "3. atr_trail_breakout — entry_N, atr_min_pct, trail_atr, h4_bias, be_at_r, hours; full budget\n"
        + "4. htf_fib_xau — after fix; sl/tp atr, rsi filter on/off, require bias, BE; full budget even if prior n=0\n"
        + "5. htf_pullback_new — NEW: H4 up + pull to ema20/50 + rsi band + optional FVG-proxy (gap from prior 3-bar impulse); full budget\n\n"
        + "### Search discipline\n"
        + "- Per lane: at least 200 evals OR full cartesian of a designed grid (whichever smaller but try for 300–800 if fast)\n"
        + "- If a lane's best develop score is weak, STILL run a second-stage neighborhood refine (local grid ± around best) before marking 'exhausted'\n"
        + "- Record for each lane: n_evals, best_params, develop_metrics, pseudo_val_metrics, exhausted=true, kill_candidate=false unless soft floor fails after refine\n"
        + "- Soft floor develop to mark struggling: PF<1.1 AND n<15 AND NP<=0 after full budget → 'struggling' not discarded yet\n"
        + "- Write results/xau_lane_deep_opt.json with all lanes\n"
        + "- Freeze champions: top 1 per lane by develop objective (and top 2 overall) into results/xau_lane_champions.json WITHOUT holdout numbers\n\n"
        + "Run the script; fix bugs until JSON written.\n"
        + "Return ok=true if all 5 lanes have exhausted=true and champions frozen. summary = best develop PF/n per lane.",
    #{
        label: "deep-opt",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("SealedHoldout");
log("Single sealed holdout pass on frozen champions only");
let holdout = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "SAFETY: offline only. ONE evaluation pass. Do not retune after seeing results.\n"
        + "Read results/xau_lane_champions.json (frozen).\n"
        + "Evaluate each champion on holdout time>=2026-01-01 using same simulators as deep opt.\n"
        + "Hard gates: PF>1.5, WR>55, DD<10, n>=20 → hard_pass\n"
        + "Also report expectancy, net_profit, underpowered if n<20.\n"
        + "Write results/xau_lane_holdout_eval.json\n"
        + "Write results/xau_lane_survivors.json with survivors (hard_pass only) and struggling_but_improved notes\n"
        + "If any hard_pass: write results/xau_candidate_params.json for best survivor by holdout net_profit\n"
        + "CRITICAL: do not change champions after seeing holdout.\n"
        + "Return ok=true if eval written. summary = hard_pass count + best holdout lane.",
    #{
        label: "sealed-holdout",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("Skeptic");
log("Skeptic: early-discard audit + overfit");
let skeptic = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "Hostile review. Read charter, deep_opt.json, champions, holdout_eval, fib_fix_note, xcom notes.\n"
        + "Write results/xau_lane_deep_opt_skeptic.md:\n"
        + "1. Did every lane exhaust develop budget? Any early discard?\n"
        + "2. Holdout leakage into param choice?\n"
        + "3. Fib confirmation fixed?\n"
        + "4. X.com ideas actually coded vs cargo-cult?\n"
        + "5. Multiple testing / overfit risk\n"
        + "6. real survivors only with hard gates + clean protocol\n"
        + "7. Per-lane KEEP_OPTIMIZING vs PARK vs KILL with justification (KILL only if budget exhausted AND develop+holdout both hopeless)\n"
        + "Return ok=true if written. summary = survive count + per-lane status.",
    #{
        label: "skeptic",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("Report");
let a_ok = ingest != () && ingest.success && ingest.output != () && ingest.output.ok == true;
let f_ok = fixfib != () && fixfib.success && fixfib.output != () && fixfib.output.ok == true;
let d_ok = deep != () && deep.success && deep.output != () && deep.output.ok == true;
let h_ok = holdout != () && holdout.success && holdout.output != () && holdout.output.ok == true;
let s_ok = skeptic != () && skeptic.success && skeptic.output != () && skeptic.output.ok == true;

fn sum_of(r) {
    if r != () && r.success && r.output != () && r.output.summary != () {
        return r.output.summary;
    }
    return "n/a";
}

let report = agent(
    "Write /home/yderf/Projects/trading/mt5-arch-integration/results/xau_lane_deep_opt_summary.md\n"
        + "Never recommend --live. Prefer KEEP_OPTIMIZING over KILL when evidence mixed.\n"
        + "Read all xau_lane_* and xau_xcom_research_notes.md artifacts.\n"
        + "Phases: INGEST=" + a_ok.to_string() + " " + json_encode(sum_of(ingest))
        + " FIB=" + f_ok.to_string() + " " + json_encode(sum_of(fixfib))
        + " DEEP=" + d_ok.to_string() + " " + json_encode(sum_of(deep))
        + " HOLDOUT=" + h_ok.to_string() + " " + json_encode(sum_of(holdout))
        + " SKEPTIC=" + s_ok.to_string() + " " + json_encode(sum_of(skeptic)) + "\n"
        + "Structure:\n"
        + "# XAU lane deep optimization\n"
        + "## Safety\n## X.com ideas incorporated\n## Per-lane develop opt (budget, best metrics)\n## Sealed holdout table\n## Skeptic keep/park/kill\n## Survivors or none\n## Next steps (continue optimizing which lanes)\n"
        + "Return ok=true if written. summary = one-line overall + which lanes to keep optimizing.",
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

let all_ok = a_ok && f_ok && d_ok && h_ok && s_ok && r_ok;
let scratch = "# XAU lane deep opt\n\n"
    + "- ingest: " + a_ok.to_string() + " — " + sum_of(ingest) + "\n"
    + "- fib_fix: " + f_ok.to_string() + " — " + sum_of(fixfib) + "\n"
    + "- deep_opt: " + d_ok.to_string() + " — " + sum_of(deep) + "\n"
    + "- holdout: " + h_ok.to_string() + " — " + sum_of(holdout) + "\n"
    + "- skeptic: " + s_ok.to_string() + " — " + sum_of(skeptic) + "\n"
    + "- report: " + r_ok.to_string() + " — " + r_sum + "\n"
    + "- doctrine: never discard early; X.com informed; no --live\n";

let path = write_scratch_file("xau_lane_deep_opt.md", scratch);
log(scratch);

complete(#{
    summary: r_sum,
    all_ok: all_ok,
    ingest_ok: a_ok,
    fib_ok: f_ok,
    deep_ok: d_ok,
    holdout_ok: h_ok,
    skeptic_ok: s_ok,
    report_ok: r_ok,
    scratch: path,
    report_path: "results/xau_lane_deep_opt_summary.md",
});
