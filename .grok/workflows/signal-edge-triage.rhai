let meta = #{
    name: "signal-edge-triage",
    description: "Triage closed SCREEN_FAIL families: DEAD vs COST-BOUND vs ANTI vs CLEARS-FRICTION",
    phases: [
        #{ title: "Inventory", detail: "enumerate closed families + runnable signal wiring" },
        #{ title: "Adapters", detail: "extend signal_edge_diagnostic.py with thin lane adapters" },
        #{ title: "Diagnose", detail: "develop-only diagnostic + EURUSD regression gate" },
        #{ title: "Report", detail: "write SIGNAL-EDGE-TRIAGE.md and commit on branch" },
    ],
};

let inv_schema = #{
    "type": "object",
    "required": ["ok", "families", "n_families", "n_runnable", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        families: #{
            "type": "array",
            "items": #{
                "type": "object",
                "required": ["family_id", "lane", "runnable"],
                "properties": #{
                    family_id: #{ "type": "string" },
                    lane: #{ "type": "string" },
                    writeup_path: #{ "type": "string" },
                    lock_path: #{ "type": "string" },
                    holdout_boundary: #{ "type": "string" },
                    module_path: #{ "type": "string" },
                    signal_fn: #{ "type": "string" },
                    data_csv: #{ "type": "string" },
                    friction_pts: #{ "type": "number" },
                    runnable: #{ "type": "boolean" },
                    skip_reason: #{ "type": "string" },
                },
            },
        },
        n_families: #{ "type": "integer" },
        n_runnable: #{ "type": "integer" },
        evidence: #{ "type": "string" },
    },
};

let adapt_schema = #{
    "type": "object",
    "required": ["ok", "adapters_added", "families_skipped", "lint_clean", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        adapters_added: #{ "type": "array", "items": #{ "type": "string" } },
        families_skipped: #{
            "type": "array",
            "items": #{
                "type": "object",
                "required": ["family_id", "reason"],
                "properties": #{
                    family_id: #{ "type": "string" },
                    reason: #{ "type": "string" },
                },
            },
        },
        lint_clean: #{ "type": "boolean" },
        evidence: #{ "type": "string" },
    },
};

let diag_schema = #{
    "type": "object",
    "required": ["ok", "results", "eurusd_regression_ok", "n_dead", "n_cost_bound", "n_anti", "n_clears_friction", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        results: #{
            "type": "array",
            "items": #{
                "type": "object",
                "required": ["family_id", "lane", "verdict"],
                "properties": #{
                    family_id: #{ "type": "string" },
                    lane: #{ "type": "string" },
                    n_signals: #{ "type": "integer" },
                    best_horizon: #{ "type": "integer" },
                    best_mean_pts: #{ "type": "number" },
                    best_t: #{ "type": "number" },
                    friction_pts: #{ "type": "number" },
                    verdict: #{ "type": "string" },
                },
            },
        },
        eurusd_regression_ok: #{ "type": "boolean" },
        n_dead: #{ "type": "integer" },
        n_cost_bound: #{ "type": "integer" },
        n_anti: #{ "type": "integer" },
        n_clears_friction: #{ "type": "integer" },
        evidence: #{ "type": "string" },
    },
};

let report_schema = #{
    "type": "object",
    "required": ["ok", "report_path", "branch", "commit_sha", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        report_path: #{ "type": "string" },
        branch: #{ "type": "string" },
        commit_sha: #{ "type": "string" },
        evidence: #{ "type": "string" },
    },
};

let wt = if args == () { () } else { args.worktree };
if wt == () {
    pause("verification", "Pass args.worktree — path to .worktrees/mt5-arch-integration/signal-triage");
}

let hard_rules = "";
hard_rules += "HARD RULES (non-negotiable):\n";
hard_rules += "1. DEVELOP WINDOWS ONLY. Read each lane lock holdout; never widen; never peek holdout.\n";
hard_rules += "2. DO NOT RE-IMPLEMENT closed-family signals. Import existing modules only; else runnable=false.\n";
hard_rules += "3. NO lock/charter/xau_loop_status edits. No screen/grid/null re-runs. promote=false live_go=false.\n";
hard_rules += "4. COST-BOUND does NOT revive a family — evidence for a future NEW family_id only.\n";
hard_rules += "5. DO NOT invert ANTI families.\n";
hard_rules += "6. Research scripts: plain python3 (not uv run). Lint: uv run ruff check.\n";
hard_rules += "7. Tool scripts/signal_edge_diagnostic.py is read-only measurement only.\n";

phase("Inventory");
let inv_prompt = "";
inv_prompt += "Work ONLY in worktree cwd: " + wt + "\n";
inv_prompt += hard_rules;
inv_prompt += "Phase Inventory (read-only tools: read_file, grep, list_dir).\n";
inv_prompt += "Enumerate EVERY closed research family from:\n";
inv_prompt += "- results/xau_loop_status.md (~10 dead XAU families)\n";
inv_prompt += "- results/us_index_session_v*.md (8 screens)\n";
inv_prompt += "- results/eurusd_ny_scalp_autoresearch.md / eurusd write-ups\n";
inv_prompt += "- results/xau_charters/*.json and *_lock.json without a corresponding live screen if closed\n";
inv_prompt += "For each family return: family_id, lane, writeup_path, lock_path, holdout_boundary,\n";
inv_prompt += "module_path + signal_fn (if importable), data_csv, friction_pts (round-trip points), runnable bool,\n";
inv_prompt += "skip_reason if not runnable. Do NOT invent signal code. Set ok=true only after reading sources.\n";
inv_prompt += "Write a JSON inventory also to scratch/signal-triage-inventory.json via shell if helpful,\n";
inv_prompt += "but your schema output is authoritative.\n";
let inv = agent(inv_prompt, #{
    label: "inventory",
    capability_mode: "read-only",
    cwd: wt,
    output_schema: inv_schema,
});
if inv == () || !inv.success || inv.output == () || inv.output.ok != true {
    complete(#{
        ok: false,
        summary: "Inventory failed or unverified",
        inventory: inv,
    });
}
log("inventory: " + inv.output.n_families.to_string() + " families, " + inv.output.n_runnable.to_string() + " runnable");

phase("Adapters");
let adapt_prompt = "";
adapt_prompt += "Work ONLY in worktree cwd: " + wt + "\n";
adapt_prompt += hard_rules;
adapt_prompt += "Phase Adapters (execute). Inventory JSON follows — trust only runnable=true rows:\n";
adapt_prompt += json_encode(inv.output.families) + "\n";
adapt_prompt += "Extend scripts/signal_edge_diagnostic.py:\n";
adapt_prompt += "- Keep forward_edge/format_table/_eurusd_families generic/intact.\n";
adapt_prompt += "- Add thin adapters per runnable lane (import frozen signal producers; never reimplement).\n";
adapt_prompt += "- Add --lane CLI (eurusd|xau|us_index|all as appropriate).\n";
adapt_prompt += "- Stay read-only at runtime (diagnostic writes nothing).\n";
adapt_prompt += "- Run: uv run ruff check scripts/signal_edge_diagnostic.py\n";
adapt_prompt += "Set ok=true only if lint_clean and at least the EURUSD adapter still works.\n";
adapt_prompt += "List families_skipped with reasons for non-runnable / unwirable rows.\n";
let adapt = agent(adapt_prompt, #{
    label: "adapters",
    capability_mode: "execute",
    cwd: wt,
    output_schema: adapt_schema,
});
if adapt == () || !adapt.success || adapt.output == () || adapt.output.ok != true {
    complete(#{
        ok: false,
        summary: "Adapters failed or lint unclean",
        inventory: inv.output,
        adapters: adapt,
    });
}

phase("Diagnose");
let diag_prompt = "";
diag_prompt += "Work ONLY in worktree cwd: " + wt + "\n";
diag_prompt += hard_rules;
diag_prompt += "Phase Diagnose (execute). Run scripts/signal_edge_diagnostic.py with plain python3.\n";
diag_prompt += "Horizons 5,10,20,50,100. Develop-only masks from each lane lock. --by-year at peak horizon.\n";
diag_prompt += "SANITY GATE (must pass or ok=false and STOP):\n";
diag_prompt += "Re-run EURUSD lane and reproduce approximately:\n";
diag_prompt += "  trend_continuation ANTI (~ -11.85 at H50, t ~ -3.13)\n";
diag_prompt += "  mean_reversion COST-BOUND (~ +11.75, t ~ +4.14)\n";
diag_prompt += "  breakout DEAD (~ -19.18, t ~ -1.68)\n";
diag_prompt += "If EURUSD regression fails, set eurusd_regression_ok=false, ok=false, do not trust other lanes.\n";
diag_prompt += "If EVERY family is CLEARS-FRICTION, treat as adapter bug: ok=false.\n";
diag_prompt += "Record results array + counts n_dead, n_cost_bound, n_anti, n_clears_friction.\n";
let diag = agent(diag_prompt, #{
    label: "diagnose",
    capability_mode: "execute",
    cwd: wt,
    output_schema: diag_schema,
});
if diag == () || !diag.success || diag.output == () || diag.output.ok != true {
    complete(#{
        ok: false,
        summary: "Diagnose failed or EURUSD regression / all-CLEARS bug",
        inventory: inv.output,
        adapters: adapt.output,
        diagnose: diag,
    });
}
if diag.output.eurusd_regression_ok != true {
    complete(#{
        ok: false,
        summary: "EURUSD regression gate failed — adapters changed behaviour",
        diagnose: diag.output,
    });
}

phase("Report");
let rep_prompt = "";
rep_prompt += "Work ONLY in worktree cwd: " + wt + "\n";
rep_prompt += hard_rules;
rep_prompt += "Phase Report (execute). Write docs/research/SIGNAL-EDGE-TRIAGE.md with:\n";
rep_prompt += "- one row per family: n, best horizon, edge pts, t, friction, verdict\n";
rep_prompt += "- per-lane summary\n";
rep_prompt += "- explicit section: COST-BOUND does not authorize revival; ANTI must not be inverted\n";
rep_prompt += "- unmeasurable families + reasons (finding, not omission)\n";
rep_prompt += "- EURUSD regression confirmation\n";
rep_prompt += "Use diagnose results:\n";
rep_prompt += json_encode(diag.output) + "\n";
rep_prompt += "Skipped:\n";
rep_prompt += json_encode(adapt.output.families_skipped) + "\n";
rep_prompt += "Git: ensure on branch research/signal-edge-triage. Commit report + diagnostic script changes only.\n";
rep_prompt += "Do NOT merge, do NOT open a PR, do NOT delete the worktree, do NOT edit xau_loop_status.md.\n";
rep_prompt += "Return report_path, branch, commit_sha. ok=true only after commit succeeds.\n";
let rep = agent(rep_prompt, #{
    label: "report",
    capability_mode: "execute",
    cwd: wt,
    output_schema: report_schema,
});
if rep == () || !rep.success || rep.output == () || rep.output.ok != true {
    complete(#{
        ok: false,
        summary: "Report/commit failed",
        inventory: inv.output,
        adapters: adapt.output,
        diagnose: diag.output,
        report: rep,
    });
}

let summary = "";
summary += "# signal-edge-triage\n\n";
summary += "- n_families: " + inv.output.n_families.to_string() + "\n";
summary += "- n_runnable: " + inv.output.n_runnable.to_string() + "\n";
summary += "- DEAD: " + diag.output.n_dead.to_string() + "\n";
summary += "- COST-BOUND: " + diag.output.n_cost_bound.to_string() + "\n";
summary += "- ANTI: " + diag.output.n_anti.to_string() + "\n";
summary += "- CLEARS-FRICTION: " + diag.output.n_clears_friction.to_string() + "\n";
summary += "- eurusd_regression_ok: true\n";
summary += "- branch: " + rep.output.branch + "\n";
summary += "- commit: " + rep.output.commit_sha + "\n";
summary += "- report: " + rep.output.report_path + "\n";
let path = write_scratch_file("signal-edge-triage-summary.md", summary);
complete(#{
    ok: true,
    summary: "signal-edge-triage complete",
    n_families: inv.output.n_families,
    n_runnable: inv.output.n_runnable,
    n_dead: diag.output.n_dead,
    n_cost_bound: diag.output.n_cost_bound,
    n_anti: diag.output.n_anti,
    n_clears_friction: diag.output.n_clears_friction,
    eurusd_regression_ok: true,
    branch: rep.output.branch,
    commit_sha: rep.output.commit_sha,
    report_path: rep.output.report_path,
    path: path,
});
