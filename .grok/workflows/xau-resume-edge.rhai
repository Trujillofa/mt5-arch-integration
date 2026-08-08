let meta = #{
    name: "xau-resume-edge",
    description: "Resume edge research: Vantage commission costs, next-design charter, null-first scaffold + first low-knob family",
    phases: [
        #{ title: "Costs", detail: "Bake Vantage RAW/PRO commission into research cost assumptions" },
        #{ title: "Charter", detail: "Pre-register next design family (≤3 knobs, kill rules)" },
        #{ title: "Scaffold", detail: "Reusable family null max-stat harness" },
        #{ title: "First-family", detail: "Implement one low-knob structural thesis under full costs" },
        #{ title: "Null-smoke", detail: "Quick null smoke on first family; full null if grid small" },
        #{ title: "Status-commit", detail: "Update loop status, commit, ordinary push" },
    ],
    when_to_use: "After RESEARCH_IDLE; resume edge work with costs + new design protocol (not re-mining killed lines)",
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
phase("Costs");
log("Record Vantage commission and update research cost defaults");

let costs_prompt = "";
costs_prompt += "Repo: " + root + "\n";
costs_prompt += "SAFETY: offline only. NEVER --live. Do not re-search bb_rsi or Donchian grids.\n\n";
costs_prompt += "Owner-provided Vantage commission (account-type, not symbol-specific):\n";
costs_prompt += "- RAW ECN: $3.00 per side per lot\n";
costs_prompt += "- PRO ECN: $1.50 per side per lot\n";
costs_prompt += "backtest.simulate already does 2 * commission_per_lot * lots for round trip.\n\n";
costs_prompt += "Tasks:\n";
costs_prompt += "1. Write results/xau_research_costs.json as the research cost source of truth:\n";
costs_prompt += "   {\n";
costs_prompt += "     \"broker\": \"Vantage\",\n";
costs_prompt += "     \"spread_col\": \"spread\",\n";
costs_prompt += "     \"point_size\": 0.01,\n";
costs_prompt += "     \"commission_per_lot\": 3.0,\n";
costs_prompt += "     \"commission_account_type\": \"RAW_ECN\",\n";
costs_prompt += "     \"commission_notes\": \"per side per lot; RT = 2*commission_per_lot*lots\",\n";
costs_prompt += "     \"commission_alternatives\": {\"RAW_ECN\": 3.0, \"PRO_ECN\": 1.5},\n";
costs_prompt += "     \"slippage_points\": 0.0,\n";
costs_prompt += "     \"slippage_notes\": \"still unmeasured; leave 0 until demo fills\",\n";
costs_prompt += "     \"default_reason\": \"RAW is the conservative research floor; switch to 1.5 for PRO sensitivity\"\n";
costs_prompt += "   }\n";
costs_prompt += "2. Update strategy_params.json costs.commission_per_lot to 3.0 (keep other cost fields).\n";
costs_prompt += "   Do NOT re-search params; optionally re-simulate existing params with new costs and record\n";
costs_prompt += "   metrics_with_raw_commission in results/xau_cost_sensitivity_vantage.json (dead baseline is for documentation only).\n";
costs_prompt += "3. Add a small helper in a new module scripts/xau_research_costs.py:\n";
costs_prompt += "   load_research_costs() -> dict reading results/xau_research_costs.json with fallback to strategy_params costs.\n";
costs_prompt += "4. Point scripts/xau_walkforward.py and scripts/xau_null_maxstat.py / xau_donchian_null_maxstat.py\n";
costs_prompt += "   and xau_frozen_multi_year_eval.py / xau_lane_deep_opt cost defaults to load_research_costs() if easy;\n";
costs_prompt += "   at minimum new scripts must use it. Prefer minimal churn on old scripts if import is messy.\n";
costs_prompt += "5. Write results/xau_cost_update_vantage.md documenting RAW vs PRO and the RT formula.\n\n";
costs_prompt += "Return ok=true if costs JSON exists and commission_per_lot defaults to 3.0. summary = RT $ for 0.01 and 1.0 lot RAW.";

let costs_r = agent(
    costs_prompt,
    #{
        label: "vantage-commission",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

if costs_r == () || !costs_r.success || costs_r.output.ok != true {
    complete(#{
        ok: false,
        summary: "Cost update failed; abort resume",
        details: "costs phase failed",
    });
}

// ---------------------------------------------------------------------------
phase("Charter");
log("Pre-register next design family charter");

let ch_prompt = "";
ch_prompt += "Repo: " + root + "\n";
ch_prompt += "SAFETY: pre-register only; do not mine holdout. Dead lines: bb_rsi, Donchian — do not revive.\n\n";
ch_prompt += "Write results/xau_next_design_charter.md with a FROZEN research program for the next family:\n\n";
ch_prompt += "Recommended thesis A (structural, low knob):\n";
ch_prompt += "  Name: session_or_breakout_fixed (pick one concrete rule)\n";
ch_prompt += "  Hypothesis: one sentence economic claim (who pays you).\n";
ch_prompt += "  Instrument: XAUUSD H1 first; optional multi-symbol later.\n";
ch_prompt += "  Free knobs: AT MOST 3 (list exact axes and allowed values). Everything else fixed.\n";
ch_prompt += "  Fixed: risk_pct=0.01, long_only policy, costs from xau_research_costs.json (RAW $3/side).\n";
ch_prompt += "  Window: develop time < holdout_start; holdout NEVER for selection.\n";
ch_prompt += "  Success: null max-stat p_max_pf<=0.05 AND p_n_passers<=0.05 AND costed walk-forward not negative.\n";
ch_prompt += "  Kill: fail null or fail WF → KILL family; no refine loops.\n";
ch_prompt += "  Explicitly forbidden: re-grid bb_rsi/Donchian; early-exit search; frictionless eval.\n\n";
ch_prompt += "Also write machine-readable results/xau_next_design_charter.json with the same fields.\n";
ch_prompt += "Pick a concrete first family that is implementable in one session, e.g.:\n";
ch_prompt += "  - fixed_hours_ema_trend: long if close>ema200, hours in {12..20}, SL=k*ATR, TP=r*SL with only k,r free (or fixed 1.5/2.0)\n";
ch_prompt += "  - or prior_day_high_break: long when H1 close > prior day high, SL=1.5 ATR, TP=2.5 ATR, hours fixed — 0–1 knobs\n";
ch_prompt += "Prefer fewer knobs.\n\n";
ch_prompt += "Return ok=true if both md+json exist and knobs<=3. summary = family name + knobs.";

let ch_r = agent(
    ch_prompt,
    #{
        label: "next-design-charter",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

if ch_r == () || !ch_r.success || ch_r.output.ok != true {
    complete(#{
        ok: false,
        summary: "Charter failed",
        details: "charter phase failed",
    });
}

// ---------------------------------------------------------------------------
phase("Scaffold");
log("Reusable family null max-stat harness");

let sc_prompt = "";
sc_prompt += "Repo: " + root + "\n";
sc_prompt += "Implement scripts/xau_family_null_maxstat.py — reusable harness modeled on scripts/xau_null_maxstat.py:\n";
sc_prompt += "- load_research_costs() for costs\n";
sc_prompt += "- develop_only window via holdout_start\n";
sc_prompt += "- scramble_ohlc return-shuffle nulls (reuse from xau_null_maxstat or import shared helper)\n";
sc_prompt += "- CLI: --family NAME --n-null --max-n --workers --quick --seed\n";
sc_prompt += "- Plugin style: import a family module or switch that provides grid() and simulate(d, **params)\n";
sc_prompt += "- Writes results/xau_{family}_null_maxstat.{json,md}\n";
sc_prompt += "- Gates: classic + optional soft; max-stat gated on n_trades>=20\n";
sc_prompt += "- Decision rule same as before (KILL if p>0.05)\n\n";
sc_prompt += "Factor shared scramble/score helpers into scripts/xau_null_core.py if that reduces duplication with existing null scripts.\n";
sc_prompt += "Smoke: --quick must exit 0 for a stub/test family OR for the first family once implemented.\n\n";
sc_prompt += "Return ok=true if harness exists and imports clean. summary = entrypoint CLI.";

let sc_r = agent(
    sc_prompt,
    #{
        label: "null-scaffold",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

// ---------------------------------------------------------------------------
phase("First-family");
log("Implement first low-knob family from charter under full costs");

let ff_prompt = "";
ff_prompt += "Repo: " + root + "\n";
ff_prompt += "SAFETY: develop only for any search; costs from load_research_costs(); never --live.\n";
ff_prompt += "Read results/xau_next_design_charter.json and implement that family.\n\n";
ff_prompt += "Create scripts/xau_family_<name>.py (or scripts/families/<name>.py) with:\n";
ff_prompt += "- prepare(d) if needed (indicators)\n";
ff_prompt += "- simulate(d, **params) charging costs kwargs\n";
ff_prompt += "- build_grid() respecting ≤3 free knobs from charter (include fixed seeds)\n";
ff_prompt += "- Register with xau_family_null_maxstat.py\n\n";
ff_prompt += "Also a small develop scorer scripts/xau_family_eval.py or CLI on the family module that prints costed metrics for each grid point on develop (no early exit).\n";
ff_prompt += "Run develop full-grid once with costs (RAW $3) and write results/xau_<family>_develop_grid.json summarizing max PF, n_passers, best params.\n";
ff_prompt += "Do NOT claim edge yet — just implement + develop score.\n\n";
ff_prompt += "Return ok=true if grid scores written. summary = best develop PF + n_passers under full costs.";

let ff_r = agent(
    ff_prompt,
    #{
        label: "impl-first-family",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

// ---------------------------------------------------------------------------
phase("Null-smoke");
log("Null test first family (full if grid small; else n_null=40)");

let nu_prompt = "";
nu_prompt += "Repo: " + root + "\n";
nu_prompt += "Run null max-stat for the new family using scripts/xau_family_null_maxstat.py.\n";
nu_prompt += "If grid size <= 50: --n-null 40 --workers 8 full run.\n";
nu_prompt += "If grid size > 200: still run full n_null=40 (budget time); use max_n from charter.\n";
nu_prompt += "If runtime too long, run --n-null 20 minimum and document.\n\n";
nu_prompt += "Write disposition into the standard results files.\n";
nu_prompt += "If KILL: that is a valid success of the scientific process — do not retune.\n";
nu_prompt += "If PASS: note next is walk-forward only (do not promote).\n\n";
nu_prompt += "Return ok=true if null artifacts exist with disposition. summary = disposition + p-values.";

let nu_r = agent(
    nu_prompt,
    #{
        label: "null-first-family",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

// ---------------------------------------------------------------------------
phase("Status-commit");
log("Update status, tests, commit, push");

let st_prompt = "";
st_prompt += "Repo: " + root + "\n";
st_prompt += "SAFETY: ordinary push only. No force-push. No --live. No merge.\n\n";
st_prompt += "1. Prepend results/xau_loop_status.md: cost update (RAW $3), next design family name, null disposition, next_step.\n";
st_prompt += "   If null kill: next_step can be NEXT_FAMILY or RESEARCH_IDLE_PENDING_NEW_THESIS.\n";
st_prompt += "   If null pass: next_step = costed walk-forward for that family only.\n";
st_prompt += "2. uv run pytest tests/test_xau_pipeline.py tests/test_cli_unit.py -q\n";
st_prompt += "3. Stage research resume files (costs, charter, scaffold, family, results, workflow). Not .omo/\n";
st_prompt += "4. Commit with message describing commission RAW $3 + family name + null disposition\n";
st_prompt += "5. git push origin HEAD\n";
st_prompt += "6. Write results/xau_resume_edge_summary.md\n\n";
st_prompt += "Return ok=true if commit+push ok. summary = hash + disposition.";

let st_r = agent(
    st_prompt,
    #{
        label: "status-commit-push",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

// ---------------------------------------------------------------------------
let c_ok = costs_r != () && costs_r.success && costs_r.output.ok == true;
let h_ok = ch_r != () && ch_r.success && ch_r.output.ok == true;
let s_ok = sc_r != () && sc_r.success && sc_r.output.ok == true;
let f_ok = ff_r != () && ff_r.success && ff_r.output.ok == true;
let n_ok = nu_r != () && nu_r.success && nu_r.output.ok == true;
let t_ok = st_r != () && st_r.success && st_r.output.ok == true;
let all_ok = c_ok && h_ok && s_ok && f_ok && n_ok && t_ok;

let summary = "resume-edge: ";
if all_ok {
    summary += "OK";
} else {
    summary += "PARTIAL";
}
if nu_r != () && nu_r.success && nu_r.output.summary != () {
    summary += " — " + nu_r.output.summary;
}
if st_r != () && st_r.success && st_r.output.summary != () {
    summary += " | " + st_r.output.summary;
}

let details = "";
details += "costs=" + c_ok.to_string();
details += " charter=" + h_ok.to_string();
details += " scaffold=" + s_ok.to_string();
details += " family=" + f_ok.to_string();
details += " null=" + n_ok.to_string();
details += " commit=" + t_ok.to_string();

complete(#{
    ok: all_ok,
    summary: summary,
    details: details,
});
