let meta = #{
    name: "xau-virgin-holdout",
    description: "Refresh XAU H1; if bars past last peek, sealed virgin holdout of frozen champions — else catalog freeze; no live",
    phases: [
        #{ title: "Refresh", detail: "Export/refresh data; measure new bar frontier" },
        #{ title: "FreezeCatalog", detail: "Assemble frozen champions from prior opts" },
        #{ title: "VirginEval", detail: "Sealed holdout only if virgin window exists" },
        #{ title: "Skeptic", detail: "Independence + promote audit" },
        #{ title: "Report", detail: "LIVE_GO path or wait-for-data" },
    ],
    when_to_use: "After develop KEEP_OPTIMIZING exhausted; next is virgin holdout or data refresh",
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

phase("Refresh");
log("Refresh XAU data; detect virgin frontier");
let refresh = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "SAFETY: offline only. Never --live. Never place orders.\n"
        + "1. Record current max H1 time from xauusd_data.csv BEFORE refresh:\n"
        + "   python3 -c \"import pandas as pd; d=pd.read_csv('xauusd_data.csv',parse_dates=['time']); h=d[d.timeframe=='H1']; print(h.time.min(), h.time.max(), len(h))\"\n"
        + "2. Attempt data refresh in order until success or all fail:\n"
        + "   a) bash scripts/export-xau-from-wine-mt5.sh 2>&1 | tail -50\n"
        + "   b) python3 fetch_data.py 2>&1 | tail -40\n"
        + "   If Wine/terminal down, try scripts/08-status.sh / start terminal per scripts/04-start-terminal.sh briefly, then re-export once. Do not hang forever (cap waits ~2–3 min).\n"
        + "3. Re-measure max H1 time AFTER refresh.\n"
        + "4. Virgin frontier definition for this pipeline:\n"
        + "   last_peeked_end = 2026-08-06 18:00:00+00:00 (prior shortlist/holdout data end)\n"
        + "   virgin_start = last_peeked_end + 1 hour (or first bar strictly after last_peeked_end)\n"
        + "   virgin_available = (new max H1 time > last_peeked_end) and (count of H1 bars with time > last_peeked_end) >= 24\n"
        + "5. Write results/xau_data_frontier.json with: before_max, after_max, n_h1, virgin_start, n_virgin_bars, virgin_available, refresh_ok, refresh_log_tail\n"
        + "Return ok=true if frontier JSON written (even if virgin_available=false). summary = virgin_available + n_virgin_bars + after_max.",
    #{
        label: "refresh-data",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("FreezeCatalog");
log("Assemble frozen champion catalog from prior work");
let catalog = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "SAFETY: offline only. Do not re-optimize. Do not read holdout to pick params.\n"
        + "Build results/xau_frozen_champions_catalog.json by reading existing artifacts only:\n"
        + "- results/xau_lane_champions.json (per_lane)\n"
        + "- results/xau_candidate_params.json (vol_gate)\n"
        + "- results/xau_donchian_expectancy_ablate.json (best gate-pass exit_N=8 if present)\n"
        + "- results/xau_atr_trail_trade_count.json (pack_entry20_no_atr_floor if present)\n"
        + "- results/xau_htf_fib_widen_entries.json (best gate-pass if present)\n"
        + "Each entry: {id, lane, source_file, params, develop_metrics_if_known, role: baseline_champion|refined_develop}\n"
        + "Include BOTH baseline champions AND develop-refined candidates (max ~10 total). Deduplicate identical params.\n"
        + "Do not invent params. If a file missing, skip with note.\n"
        + "Return ok=true if catalog written with >=1 entry. summary = count of frozen configs.",
    #{
        label: "freeze-catalog",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("VirginEval");
log("Sealed virgin holdout if data allows; else explicit skip");
let virgin = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "SAFETY: offline only. NEVER retune after seeing virgin metrics. Never --live.\n"
        + "Read results/xau_data_frontier.json and results/xau_frozen_champions_catalog.json\n\n"
        + "IF virgin_available is false:\n"
        + "  Write results/xau_virgin_holdout_eval.json with {\n"
        + "    skipped: true,\n"
        + "    reason: 'insufficient bars after last_peeked_end',\n"
        + "    frontier: <copy key fields>,\n"
        + "    n_evaluated: 0\n"
        + "  }\n"
        + "  Return ok=true, summary='SKIPPED no virgin bars'\n\n"
        + "IF virgin_available is true:\n"
        + "  Write/run scripts/xau_virgin_holdout_eval.py once:\n"
        + "  - Load catalog params; reuse simulators from scripts/xau_lane_deep_opt.py and/or xau_preregistered_holdout.py / fib core\n"
        + "  - Evaluate EACH frozen config on ONLY bars with time > last_peeked_end (virgin window)\n"
        + "  - Also report develop metrics as frozen diagnostics only (do not rank by develop here)\n"
        + "  - Hard gates on virgin: PF>1.5, WR>55, DD<10, n>=20 (also report underpowered if n<20)\n"
        + "  - Write results/xau_virgin_holdout_eval.json with per-config virgin metrics + hard_pass\n"
        + "  - Write results/xau_virgin_survivors.json (hard_pass only)\n"
        + "  - If any hard_pass: write results/xau_candidate_params.json from best virgin net_profit survivor (note source=virgin)\n"
        + "  - Single pass only\n"
        + "Return ok=true if eval JSON written. summary = hard_pass count or SKIPPED.",
    #{
        label: "virgin-eval",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("Skeptic");
log("Skeptic audit of virgin independence");
let skeptic = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "Read frontier, catalog, virgin eval/survivors, prior contamination notes in xau_lane_deep_opt_summary.md\n"
        + "Write results/xau_virgin_holdout_skeptic.md:\n"
        + "1. Was virgin window truly unused before? (bars after 2026-08-06 only)\n"
        + "2. If skipped: confirm correct skip, no fake promote\n"
        + "3. If evaluated: look-ahead, sample size, multiple testing across catalog size\n"
        + "4. survive real=true only with hard gates + true virgin\n"
        + "5. LIVE_GO / PAPER_GO / WAIT_DATA / NO_GO disposition\n"
        + "   LIVE_GO only if virgin hard_pass + real + n>=20 + not underpowered + skeptic approve (still recommend paper first unless evidence extraordinary)\n"
        + "   Prefer PAPER_GO over LIVE_GO even on hard_pass\n"
        + "Return ok=true if written. summary = disposition.",
    #{
        label: "skeptic",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("Report");
let r_ok = refresh != () && refresh.success && refresh.output != () && refresh.output.ok == true;
let c_ok = catalog != () && catalog.success && catalog.output != () && catalog.output.ok == true;
let v_ok = virgin != () && virgin.success && virgin.output != () && virgin.output.ok == true;
let s_ok = skeptic != () && skeptic.success && skeptic.output != () && skeptic.output.ok == true;

fn sum_of(x) {
    if x != () && x.success && x.output != () && x.output.summary != () {
        return x.output.summary;
    }
    return "n/a";
}

let report = agent(
    "Write /home/yderf/Projects/trading/mt5-arch-integration/results/xau_virgin_holdout_summary.md\n"
        + "Also update results/xau_loop_status.md with timestamp, action, live_go, stop_reason, next_step.\n"
        + "Never recommend --live unless skeptic disposition is LIVE_GO (prefer PAPER_GO).\n"
        + "Read all xau_data_frontier / frozen_champions / virgin_* artifacts.\n"
        + "Phases: REFRESH=" + r_ok.to_string() + " " + json_encode(sum_of(refresh))
        + " CATALOG=" + c_ok.to_string() + " " + json_encode(sum_of(catalog))
        + " VIRGIN=" + v_ok.to_string() + " " + json_encode(sum_of(virgin))
        + " SKEPTIC=" + s_ok.to_string() + " " + json_encode(sum_of(skeptic)) + "\n"
        + "Structure: Safety, Data frontier, Catalog, Virgin results or skip, Skeptic disposition, Next steps.\n"
        + "Return ok=true if both status files written. summary = disposition one-liner.",
    #{
        label: "report",
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

let all_ok = r_ok && c_ok && v_ok && s_ok && rep_ok;
let scratch = "# XAU virgin holdout workflow\n\n"
    + "- refresh: " + r_ok.to_string() + " — " + sum_of(refresh) + "\n"
    + "- catalog: " + c_ok.to_string() + " — " + sum_of(catalog) + "\n"
    + "- virgin: " + v_ok.to_string() + " — " + sum_of(virgin) + "\n"
    + "- skeptic: " + s_ok.to_string() + " — " + sum_of(skeptic) + "\n"
    + "- report: " + rep_ok.to_string() + " — " + rep_sum + "\n"
    + "- safety: no --live\n";

let path = write_scratch_file("xau_virgin_holdout.md", scratch);
log(scratch);

complete(#{
    summary: rep_sum,
    all_ok: all_ok,
    refresh_ok: r_ok,
    catalog_ok: c_ok,
    virgin_ok: v_ok,
    skeptic_ok: s_ok,
    report_ok: rep_ok,
    scratch: path,
    report_path: "results/xau_virgin_holdout_summary.md",
});
