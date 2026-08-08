let meta = #{
    name: "xau-donchian-null-maxstat",
    description: "Donchian turtle null / max-stat under measured spread — kill or keep research lane",
    phases: [
        #{ title: "Implement", detail: "scripts/xau_donchian_null_maxstat.py mirroring bb_rsi null protocol" },
        #{ title: "Run", detail: "Full develop grid + return-shuffle nulls with costs" },
        #{ title: "Skeptic", detail: "Disposition KILL_DONCHIAN_LINE or PASS_KEEP_FROZEN" },
        #{ title: "Status", detail: "Update xau_loop_status + commit if clean" },
    ],
    when_to_use: "After costed multi-year leaves only Donchian sign-stable; decisive offline test before more turtle work",
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
phase("Implement");
log("Build Donchian null max-stat script (mirror bb_rsi protocol)");

let impl_prompt = "";
impl_prompt += "Repo: " + root + "\n";
impl_prompt += "SAFETY: offline only. NEVER --live. NEVER place orders. Holdout sealed for selection.\n";
impl_prompt += "Do NOT retune champions. Do NOT touch bb_rsi (already KILL_BB_RSI_LINE).\n\n";
impl_prompt += "Implement scripts/xau_donchian_null_maxstat.py modeled on scripts/xau_null_maxstat.py.\n\n";
impl_prompt += "Protocol (must match):\n";
impl_prompt += "1. Window: develop only via holdout_start / develop_only from backtest (time < 2026-01-01).\n";
impl_prompt += "2. Costs: load strategy_params.json costs block; pass into simulate_donchian kwargs.\n";
impl_prompt += "3. Data: load_h1 + prepare_frame from xau_lane_deep_opt (needs donch channels, atr_pctile, day_id, etc.).\n";
impl_prompt += "4. Grid: use grid_donchian() from xau_lane_deep_opt — if huge, deterministic subsample max_n=1200 seed=42\n";
impl_prompt += "   PLUS always prepend frozen catalog Donchian entries (baseline_donchian_turtle, refined if present)\n";
impl_prompt += "   from results/xau_frozen_champions_catalog.json. No early exit — score every config.\n";
impl_prompt += "5. Simulator: simulate_donchian from xau_lane_deep_opt (already cost-wired).\n";
impl_prompt += "6. Gates for n_passers: prefer soft_pass_expectancy used for turtles if defined in frozen multi-year\n";
impl_prompt += "   (PF>=1.5, n>=40, DD<=12, expectancy>=20) OR fall back to classic passes(n>=20, PF>1.5, WR>55, DD<10).\n";
impl_prompt += "   Report BOTH classic and soft passer counts. Primary decision stats: max_pf and n_passers_soft gated on n_trades>=20\n";
impl_prompt += "   (or n>=40 for soft) so thin PF=99 cannot dominate.\n";
impl_prompt += "7. Null: same scramble_ohlc return-shuffle as xau_null_maxstat (keep time/spread calendar-aligned),\n";
impl_prompt += "   re-prepare_frame / recompute indicators each trial, re-score full grid. Default n_null=40, workers<=8.\n";
impl_prompt += "8. p-value = (hits+1)/(n_null+1) for max_pf and n_passers.\n";
impl_prompt += "9. Decision: KILL_DONCHIAN_LINE if p_max_pf>0.05 OR p_n_passers>0.05; else PASS_KEEP_FROZEN\n";
impl_prompt += "   (still promote=no / live_go=false).\n";
impl_prompt += "10. Writes: results/xau_donchian_null_maxstat.json + results/xau_donchian_null_maxstat.md\n";
impl_prompt += "11. CLI: --n-null, --max-n, --workers, --quick (max_n=40 n_null=4), --seed, --null-seed\n";
impl_prompt += "12. Reuse scramble_ohlc / score patterns from xau_null_maxstat; import prepare_frame, simulate_donchian, grid_donchian.\n\n";
impl_prompt += "Smoke: python3 scripts/xau_donchian_null_maxstat.py --quick --workers 2  must exit 0 and write artifacts.\n";
impl_prompt += "Return ok=true only if smoke passes. summary = grid size + smoke disposition.";

let impl_r = agent(
    impl_prompt,
    #{
        label: "impl-donchian-null",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

if impl_r == () || !impl_r.success || impl_r.output.ok != true {
    let det = "implement failed";
    if impl_r != () && impl_r.success && impl_r.output.details != () {
        det = impl_r.output.details;
    }
    complete(#{
        ok: false,
        summary: "Donchian null script not ready; abort full run",
        details: det,
    });
}

// ---------------------------------------------------------------------------
phase("Run");
log("Full Donchian null max-stat (40 nulls, develop, costed)");

let run_prompt = "";
run_prompt += "Repo: " + root + "\n";
run_prompt += "SAFETY: offline only. NEVER --live.\n\n";
run_prompt += "Run the FULL Donchian null test (not --quick):\n";
run_prompt += "  python3 scripts/xau_donchian_null_maxstat.py --n-null 40 --workers 8 --progress-every 200\n\n";
run_prompt += "This can take 10–20+ minutes. Do not kill early. Fix crashes and re-run until JSON+MD exist\n";
run_prompt += "with n_trials=40 (or document if reduced after a hard failure).\n\n";
run_prompt += "Print the disposition line and key table (real max_pf, n_passers, null p50, p-values).\n";
run_prompt += "Return ok=true if results/xau_donchian_null_maxstat.json and .md exist with a real disposition\n";
run_prompt += "(not QUICK_SMOKE_ONLY). summary = disposition + p_max_pf + p_n_passers.";

let run_r = agent(
    run_prompt,
    #{
        label: "run-donchian-null",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

if run_r == () || !run_r.success || run_r.output.ok != true {
    let det2 = "full run failed";
    if run_r != () && run_r.success && run_r.output.details != () {
        det2 = run_r.output.details;
    }
    complete(#{
        ok: false,
        summary: "Donchian null full run failed",
        details: det2,
    });
}

// ---------------------------------------------------------------------------
phase("Skeptic");
log("Hostile disposition from Donchian null results");

let sk_prompt = "";
sk_prompt += "Repo: " + root + "\n";
sk_prompt += "SAFETY: fail closed. promote=no unless impossible bar is cleared (it will not be).\n\n";
sk_prompt += "Read results/xau_donchian_null_maxstat.md + .json, results/xau_frozen_multi_year_costed_skeptic.md,\n";
sk_prompt += "results/xau_null_maxstat.md (bb_rsi already dead).\n\n";
sk_prompt += "Write results/xau_donchian_null_skeptic.md:\n";
sk_prompt += "1. Quote disposition and p-values\n";
sk_prompt += "2. If KILL: RESEARCH_IDLE for strategy-edge work; virgin WAIT_DATA only for process hygiene\n";
sk_prompt += "3. If PASS: still promote=no / live_go=false; only keep frozen Donchian for future sealed virgin eval\n";
sk_prompt += "4. Explicit: do not retune, do not cross-instrument yet, do not revive bb_rsi\n";
sk_prompt += "5. Housekeeping still open (charter PR, CSV history, Exness symbols, ruff)\n\n";
sk_prompt += "Return ok=true if skeptic written. summary = one-line final disposition.";

let sk_r = agent(
    sk_prompt,
    #{
        label: "donchian-null-skeptic",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

// ---------------------------------------------------------------------------
phase("Status");
log("Update loop status and commit workflow artifacts");

let st_prompt = "";
st_prompt += "Repo: " + root + "\n";
st_prompt += "1. Prepend a section to results/xau_loop_status.md for Donchian null max-stat:\n";
st_prompt += "   disposition, p-values, live_go=false, promote=no, next_step (RESEARCH_IDLE or virgin-only).\n";
st_prompt += "2. git status; stage ONLY donchian-null related files:\n";
st_prompt += "   scripts/xau_donchian_null_maxstat.py\n";
st_prompt += "   results/xau_donchian_null_maxstat.json\n";
st_prompt += "   results/xau_donchian_null_maxstat.md\n";
st_prompt += "   results/xau_donchian_null_skeptic.md\n";
st_prompt += "   results/xau_loop_status.md\n";
st_prompt += "   .grok/workflows/xau-donchian-null-maxstat.rhai (if present)\n";
st_prompt += "   Do NOT stage AGENTS.md, .omo/, unrelated edits.\n";
st_prompt += "3. Commit with a complete sentence message describing disposition and key p-values.\n";
st_prompt += "   Use HEREDOC for the message. Do NOT push unless you were told to (you were not in this phase).\n";
st_prompt += "4. Run uv run pytest tests/test_xau_pipeline.py -q — must pass.\n\n";
st_prompt += "Return ok=true if status updated and commit succeeded. summary = commit hash + disposition.";

let st_r = agent(
    st_prompt,
    #{
        label: "status-commit",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

// ---------------------------------------------------------------------------
let impl_ok = impl_r != () && impl_r.success && impl_r.output.ok == true;
let run_ok = run_r != () && run_r.success && run_r.output.ok == true;
let sk_ok = sk_r != () && sk_r.success && sk_r.output.ok == true;
let st_ok = st_r != () && st_r.success && st_r.output.ok == true;
let all_ok = impl_ok && run_ok && sk_ok && st_ok;

let summary = "donchian null: ";
if all_ok {
    summary += "OK";
} else {
    summary += "PARTIAL";
}
if run_r != () && run_r.success && run_r.output.summary != () {
    summary += " — " + run_r.output.summary;
}
if st_r != () && st_r.success && st_r.output.summary != () {
    summary += " | " + st_r.output.summary;
}

let details = "";
details += "impl=" + impl_ok.to_string();
details += " run=" + run_ok.to_string();
details += " skeptic=" + sk_ok.to_string();
details += " status=" + st_ok.to_string();

complete(#{
    ok: all_ok,
    summary: summary,
    details: details,
});
