let meta = #{
    name: "open-items-closeout",
    description: "Land orphaned .rhai + simulator-conformance + exog FAIL record as three PRs",
    phases: [
        #{ title: "Workflows", detail: "commit four orphan .rhai; remove signal-triage worktree" },
        #{ title: "Simulator", detail: "merge-clean simulator-conformance; full suite + CI green" },
        #{ title: "ExogFail", detail: "merge FAIL record for multiplicity; extraction-scope answer" },
        #{ title: "Report", detail: "per-item URLs, n_drift, scope finding, multiplicity finding" },
    ],
};

let wf_schema = #{
    "type": "object",
    "required": ["ok", "pr_url", "pr_run_url", "main_run_url", "files", "signal_triage_removed", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        pr_url: #{ "type": "string" },
        pr_run_url: #{ "type": "string" },
        main_run_url: #{ "type": "string" },
        files: #{ "type": "string" },
        signal_triage_removed: #{ "type": "boolean" },
        evidence: #{ "type": "string" },
    },
};
let sim_schema = #{
    "type": "object",
    "required": ["ok", "pr_url", "pr_run_url", "main_run_url", "pytest_before", "pytest_after", "ci_tests_count_rose", "d_lines", "holdout_identical", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        pr_url: #{ "type": "string" },
        pr_run_url: #{ "type": "string" },
        main_run_url: #{ "type": "string" },
        pytest_before: #{ "type": "string" },
        pytest_after: #{ "type": "string" },
        ci_tests_count_rose: #{ "type": "boolean" },
        d_lines: #{ "type": "integer" },
        holdout_identical: #{ "type": "boolean" },
        evidence: #{ "type": "string" },
    },
};
let exog_schema = #{
    "type": "object",
    "required": ["ok", "pr_url", "pr_run_url", "main_run_url", "n_drift", "n_claims", "n_results_tracked", "extraction_scope_answer", "multiplicity_finding", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        pr_url: #{ "type": "string" },
        pr_run_url: #{ "type": "string" },
        main_run_url: #{ "type": "string" },
        n_drift: #{ "type": "integer" },
        n_claims: #{ "type": "integer" },
        n_results_tracked: #{ "type": "integer" },
        extraction_scope_answer: #{ "type": "string" },
        multiplicity_finding: #{ "type": "string" },
        evidence: #{ "type": "string" },
    },
};
let report_schema = #{
    "type": "object",
    "required": ["ok", "report_path", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        report_path: #{ "type": "string" },
        evidence: #{ "type": "string" },
    },
};

let repo = if args == () { () } else { args.repo };
let workflows_wt = if args == () { () } else { args.workflows_wt };
let simulator_wt = if args == () { () } else { args.simulator_wt };
let exog_wt = if args == () { () } else { args.exog_wt };
if repo == () || workflows_wt == () || simulator_wt == () || exog_wt == () {
    pause("verification", "Pass args.repo, args.workflows_wt, args.simulator_wt, args.exog_wt");
}

let rules = "";
rules += "HARD: no --live; no holdout peek; do not edit results/xau_loop_status.md; ";
rules += "no screens/backtests/fetch_data/sealed_cycle/Strategy Tester; ";
rules += "no numpy/pandas in pyproject.toml; claim-audit stays stdlib-only; ";
rules += "do not force-push main; do not delete any git branch; ";
rules += "do not commit results/tick_data|eurusd_data|btc_data|.crew|.grok/state. ";
rules += "Standing RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS / promote=no / live_go=false — unchanged. ";
rules += "If a gate fails: report real output and STOP that item — no tolerance widening. ";
rules += "Paste REAL gh run URLs for both PR and post-merge main push. Use tools.\n";

// ---------------------------------------------------------------------------
phase("Workflows");
let p1 = "";
p1 += rules;
p1 += "ITEM 1 (cheapest; do first). Worktree: " + workflows_wt + " on chore/open-items-workflows (from origin/main).\n";
p1 += "Rescue these FOUR orphan .rhai (currently untracked; .gitignore deliberately un-ignores them):\n";
p1 += "  .grok/workflows/signal-edge-triage.rhai\n";
p1 += "  .grok/workflows/xau-asia-box-v2-reverify.rhai\n";
p1 += "  .grok/workflows/ci-host-python-numpy.rhai\n";
p1 += "  .grok/workflows/merge-debt-land.rhai\n";
p1 += "Copy from " + repo + "/.grok/workflows/ (and signal-triage wt if needed) into " + workflows_wt + ".\n";
p1 += "Before staging: git status --porcelain .grok/ must show ONLY those four. Do not add .grok/state or .crew.\n";
p1 += "Commit, push, open PR, wait for CI green (all 3 jobs), merge, wait for main push run green.\n";
p1 += "Paste pr_url, pr_run_url, main_run_url. files=comma-separated names.\n";
p1 += "THEN remove worktree /home/yderf/Projects/trading/.worktrees/mt5-arch-integration/signal-triage\n";
p1 += "(branch research/signal-edge-triage is 0 ahead — fully merged; remaining untracked are disposable\n";
p1 += "data symlinks + scratch/). Use git worktree remove. signal_triage_removed=true only after remove succeeds.\n";
p1 += "Do NOT delete the git branch. ok=true only if PR+main CI green and worktree removed.\n";
let wf = agent(p1, #{ label: "item1-workflows", capability_mode: "all", cwd: workflows_wt, output_schema: wf_schema });
if wf == () || !wf.success || wf.output == () || wf.output.ok != true {
    complete(#{ ok: false, summary: "Item 1 failed — stop before simulator/exog", workflows: wf });
}
if wf.output.signal_triage_removed != true {
    complete(#{ ok: false, summary: "signal-triage worktree not removed", workflows: wf.output });
}
log("Item1 done " + wf.output.pr_url);

// ---------------------------------------------------------------------------
phase("Simulator");
let p2 = "";
p2 += rules;
p2 += "ITEM 2 — land research/simulator-conformance. Worktree: " + simulator_wt + ".\n";
p2 += "REVERSAL CONTEXT: previous 'landable after rebase' upgrades to land NOW — no rebase required.\n";
p2 += "Cheap reconfirm (do not re-derive at length):\n";
p2 += "  git fetch origin main\n";
p2 += "  git merge-tree --write-tree origin/main research/simulator-conformance  -> clean\n";
p2 += "  engine diff 64e012d..origin/main for backtest.py htf_fib_core xau_*.py -> empty\n";
p2 += "  uv run pytest -q tests/test_simulator_conformance.py -> 15 passed\n";
p2 += "  uv run ruff check tests/test_simulator_conformance.py\n";
p2 += "Merge origin/main into the branch with a merge commit (do NOT rewrite the 7 commits).\n";
p2 += "Gates before push:\n";
p2 += "  1) git diff --name-status origin/main...HEAD has zero D lines (d_lines=0)\n";
p2 += "  2) holdout_identical: git diff origin/main -- results/xau_holdout_lock.json empty\n";
p2 += "  3) no mods under results/xau_charters/ or results/xau_runs/\n";
p2 += "  4) FULL suite: uv run pytest -q -m 'not live' — record pytest_before (on main tip clone or\n";
p2 += "     pre-merge) and pytest_after (on branch). Expect ~781 -> ~796 ( +15).\n";
p2 += "Open PR, wait for all 3 CI jobs green. Confirm CI tests passed count ROSE (~+15), not skipped.\n";
p2 += "Merge. Wait for SEPARATE main push run green. Paste both run URLs.\n";
p2 += "If CI fails: report --log-failed; do not skip/xfail/deselect the new tests.\n";
p2 += "ok=true only if d_lines==0, holdout_identical, both runs green, ci_tests_count_rose.\n";
let sim = agent(p2, #{ label: "item2-simulator", capability_mode: "all", cwd: simulator_wt, output_schema: sim_schema });
if sim == () || !sim.success || sim.output == () || sim.output.ok != true {
    complete(#{ ok: false, summary: "Item 2 failed", simulator: sim, workflows: wf.output });
}
if sim.output.d_lines != 0 || sim.output.holdout_identical != true || sim.output.ci_tests_count_rose != true {
    complete(#{ ok: false, summary: "Item 2 gates failed", simulator: sim.output });
}
log("Item2 done " + sim.output.pr_url);

// ---------------------------------------------------------------------------
phase("ExogFail");
let p3 = "";
p3 += rules;
p3 += "ITEM 3 — REVERSAL: do NOT close research/exog-fx-daily-cosign-xau-paper-gate — MERGE it.\n";
p3 += "Red is the RESULT, not a defect. Multiplicity accounting needs the record on main.\n";
p3 += "Worktree: " + exog_wt + ". Tip dbd16ff (+570/-0): design memo, runner, results JSON+MD.\n";
p3 += "Merge origin/main (merge commit fine). Do NOT re-run the gate, retune, change thresholds,\n";
p3 += "or present as anything other than FAIL. Landing a record, not reopening a lane.\n";
p3 += "PR/commit message MUST say: FAIL artifact for multiplicity accounting; promote=false;\n";
p3 += "live_go=false; NOT a revival of exog_london_fx_cosign_xau_follow_flat.\n";
p3 += "Verify: python3 scripts/research_claim_verify.py --fail-on-drift --out /tmp/exog-claim.json\n";
p3 += "Expect n_drift=0; record n_claims and n_results_tracked (baseline was 531 / 185; with exog\n";
p3 += "expect ~187 tracked, claims may stay 531).\n";
p3 += "Open PR, CI green, merge, main push run green. Paste URLs.\n";
p3 += "OPEN QUESTION (report only): merge adds ~2 oracles but n_claims stays 531 — should the memo\n";
p3 += "metrics table be in auditor extraction scope, or correctly out of scope? Answer with evidence\n";
p3 += "(read the memo + how verify extracts claims). If scope change warranted, SAY SO AND STOP —\n";
p3 += "do not re-derive research_claim_selfref_allow.json here (standing rule: that is its own task).\n";
p3 += "MULTIPLICITY FINDING: do NOT edit results/xau_loop_status.md. If main's dead-family / K_prior\n";
p3 += "is now inconsistent with what landed, report finding+reasoning only.\n";
p3 += "ok=true if merged, CI green both runs, n_drift==0, and both answers populated.\n";
let exog = agent(p3, #{ label: "item3-exog-fail", capability_mode: "all", cwd: exog_wt, output_schema: exog_schema });
if exog == () || !exog.success || exog.output == () || exog.output.ok != true {
    complete(#{ ok: false, summary: "Item 3 failed", exog: exog, prior: #{ workflows: wf.output, simulator: sim.output } });
}
if exog.output.n_drift != 0 {
    complete(#{ ok: false, summary: "n_drift != 0 after exog — stop", exog: exog.output });
}
log("Item3 done " + exog.output.pr_url + " n_claims=" + exog.output.n_claims.to_string());

// ---------------------------------------------------------------------------
phase("Report");
let p4 = "";
p4 += rules;
p4 += "Write " + repo + "/scratchpad/open-items-closeout-report.md covering all three items.\n";
p4 += "Include: PR numbers, PR+main run URLs with per-job conclusions, pytest before/after item 2,\n";
p4 += "post-merge n_drift/n_claims/n_results_tracked, extraction_scope_answer, multiplicity_finding,\n";
p4 += "signal-triage removal, anything left undone.\n";
p4 += "Data: workflows=" + json_encode(wf.output) + "\n";
p4 += "simulator=" + json_encode(sim.output) + "\n";
p4 += "exog=" + json_encode(exog.output) + "\n";
p4 += "report_path=that path. ok=true if written.\n";
let rep = agent(p4, #{ label: "report", capability_mode: "all", cwd: repo, output_schema: report_schema });
if rep == () || !rep.success || rep.output == () || rep.output.ok != true {
    complete(#{ ok: false, summary: "Report failed", report: rep });
}

let summary = "";
summary += "# open-items-closeout\n\n";
summary += "- Workflows: " + wf.output.pr_url + "\n";
summary += "- Simulator: " + sim.output.pr_url + "\n";
summary += "- Exog FAIL: " + exog.output.pr_url + " n_claims=" + exog.output.n_claims.to_string() + "\n";
summary += "- Report: " + rep.output.report_path + "\n";
let path = write_scratch_file("open-items-closeout-summary.md", summary);
complete(#{
    ok: true,
    summary: "three open items landed",
    path: path,
    workflows: wf.output,
    simulator: sim.output,
    exog: exog.output,
    report: rep.output,
});
