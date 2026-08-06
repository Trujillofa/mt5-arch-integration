let meta = #{
    name: "xau-frozen-multi-year",
    description: "Evaluate frozen champions on older calendar windows (2023/24/25/26 slices) — no retune, no live",
    phases: [
        #{ title: "Data", detail: "Try extend history; report available years" },
        #{ title: "Eval", detail: "Frozen catalog on year and multi-year windows" },
        #{ title: "Skeptic", detail: "Label IS vs independent; no fake promote" },
        #{ title: "Report", detail: "Tables + interpretation" },
    ],
    when_to_use: "While waiting for virgin post-peek data; stability check of frozen params on older history",
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

phase("Data");
log("Extend history if possible; inventory year coverage");
let data = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "SAFETY: offline only. Never --live.\n"
        + "Current CSV H1 starts ~2024-08 (no 2023 yet). Try to get older XAU H1 if possible:\n"
        + "1. bash scripts/export-xau-from-wine-mt5.sh 2>&1 | tail -30\n"
        + "2. python3 fetch_data.py 2>&1 | tail -40\n"
        + "3. If export only has recent history, note broker limitation — do NOT invent bars.\n"
        + "4. Write results/xau_history_coverage.json: min/max H1, bars per year (2023,2024,2025,2026), has_2023 bool, notes\n"
        + "Return ok=true if coverage JSON written. summary = year bar counts.",
    #{
        label: "history-coverage",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("Eval");
log("Frozen multi-window eval — no param search");
let eval_phase = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "SAFETY: offline only. NEVER retune. NEVER --live. Use ONLY params from results/xau_frozen_champions_catalog.json\n\n"
        + "Write and run scripts/xau_frozen_multi_year_eval.py:\n"
        + "1. Load catalog (8 frozen configs). Load H1 + same simulators as xau_lane_deep_opt / preregistered (import reuse).\n"
        + "2. Define windows (skip empty):\n"
        + "   - year_2023: [2023-01-01, 2024-01-01) if any bars\n"
        + "   - year_2024: [2024-01-01, 2025-01-01)\n"
        + "   - year_2025: [2025-01-01, 2026-01-01)\n"
        + "   - year_2026_to_peek: [2026-01-01, 2026-08-06 18:00]  # known peeked holdout-era\n"
        + "   - develop_like: time < 2026-01-01\n"
        + "   - full_available: all H1\n"
        + "   - h2_2024: [2024-07-01, 2025-01-01) if useful\n"
        + "   - h1_2025: [2025-01-01, 2025-07-01)\n"
        + "   - h2_2025: [2025-07-01, 2026-01-01)\n"
        + "3. For each catalog entry × each non-empty window: metrics (PF, WR, DD, n, NP, expectancy)\n"
        + "4. hard_pass_classic: PF>1.5 WR>55 DD<10 n>=20\n"
        + "5. soft_pass_expectancy (for turtles): PF>=1.5 n>=40 DD<=12 exp>=20 (WR diagnostic only)\n"
        + "6. Write results/xau_frozen_multi_year_eval.json\n"
        + "7. Also write a compact CSV results/xau_frozen_multi_year_matrix.csv (id,window,pf,wr,dd,n,np,hard_pass)\n"
        + "Run script; fix bugs until JSON+CSV exist.\n"
        + "Return ok=true if written. summary = which years available + how many hard_pass cells.",
    #{
        label: "multi-year-eval",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("Skeptic");
log("Label contamination: develop years are IS for most champs");
let skeptic = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "Read multi-year eval + catalog + history coverage.\n"
        + "Write results/xau_frozen_multi_year_skeptic.md:\n"
        + "1. 2024–2025 windows are largely IN-SAMPLE for develop-selected champs (not independent proof).\n"
        + "2. 2026_to_peek is already-contaminated holdout era — diagnostic only.\n"
        + "3. If 2023 missing, say so — cannot claim multi-year depth.\n"
        + "4. Which lanes are stable across years (sign of PF/NP) vs collapse in one year?\n"
        + "5. Explicit: this run does NOT unlock PAPER_GO/LIVE_GO by itself.\n"
        + "6. What would count as stronger evidence (virgin post-peek, or true pre-sample 2023 if obtained without refit).\n"
        + "Return ok=true if written. summary = stability one-liner + promote=no.",
    #{
        label: "skeptic",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("Report");
let d_ok = data != () && data.success && data.output != () && data.output.ok == true;
let e_ok = eval_phase != () && eval_phase.success && eval_phase.output != () && eval_phase.output.ok == true;
let s_ok = skeptic != () && skeptic.success && skeptic.output != () && skeptic.output.ok == true;

fn sum_of(x) {
    if x != () && x.success && x.output != () && x.output.summary != () {
        return x.output.summary;
    }
    return "n/a";
}

let report = agent(
    "Write results/xau_frozen_multi_year_summary.md in /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "Update results/xau_loop_status.md briefly.\n"
        + "Never recommend --live. Clarify IS vs peeked windows in plain language.\n"
        + "Read JSON/CSV/skeptic; tables: per lane × year metrics.\n"
        + "Phases: DATA=" + d_ok.to_string() + " " + json_encode(sum_of(data))
        + " EVAL=" + e_ok.to_string() + " " + json_encode(sum_of(eval_phase))
        + " SKEPTIC=" + s_ok.to_string() + " " + json_encode(sum_of(skeptic)) + "\n"
        + "Return ok=true if summary written. summary = coverage + stability headline.",
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

let all_ok = d_ok && e_ok && s_ok && r_ok;
let scratch = "# frozen multi-year\n"
    + "- data: " + d_ok.to_string() + " " + sum_of(data) + "\n"
    + "- eval: " + e_ok.to_string() + " " + sum_of(eval_phase) + "\n"
    + "- skeptic: " + s_ok.to_string() + " " + sum_of(skeptic) + "\n"
    + "- report: " + r_ok.to_string() + " " + r_sum + "\n";
let path = write_scratch_file("xau_frozen_multi_year.md", scratch);
log(scratch);

complete(#{
    summary: r_sum,
    all_ok: all_ok,
    data_ok: d_ok,
    eval_ok: e_ok,
    skeptic_ok: s_ok,
    report_ok: r_ok,
    scratch: path,
    report_path: "results/xau_frozen_multi_year_summary.md",
});
