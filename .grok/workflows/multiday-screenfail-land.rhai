let meta = #{
    name: "multiday-screenfail-land",
    description: "Land multi_day_variance_expansion_flat SCREEN_FAIL record; keep BOTH loop_status entries",
    phases: [
        #{ title: "Prep", detail: "clean WT; confirm null_maxstat; stale-doc trap report" },
        #{ title: "CherryPick", detail: "recreate from main; cherry-pick both commits; resolve conflict" },
        #{ title: "Gates", detail: "behind/D/holdout/loop_status/charters/pytest/ruff/auditor" },
        #{ title: "PRAndCI", detail: "open PR; green PR+main push runs" },
        #{ title: "Report", detail: "order rationale; multiplicity inconsistency; URLs" },
    ],
};

let prep_schema = #{
    "type": "object",
    "required": ["ok", "null_maxstat_unchanged", "stale_docs_safe", "stale_docs_report", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        null_maxstat_unchanged: #{ "type": "boolean" },
        stale_docs_safe: #{ "type": "boolean" },
        stale_docs_report: #{ "type": "string" },
        evidence: #{ "type": "string" },
    },
};
let cherry_schema = #{
    "type": "object",
    "required": ["ok", "order_chosen", "order_rationale", "commit_shas", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        order_chosen: #{ "type": "string" },
        order_rationale: #{ "type": "string" },
        commit_shas: #{ "type": "string" },
        evidence: #{ "type": "string" },
    },
};
let gates_schema = #{
    "type": "object",
    "required": ["ok", "behind", "d_lines", "holdout_identical", "loop_status_deletions", "charters_ok", "pytest_before", "pytest_after", "count_rose", "ruff_ok", "n_drift", "n_claims", "n_results_tracked", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        behind: #{ "type": "integer" },
        d_lines: #{ "type": "integer" },
        holdout_identical: #{ "type": "boolean" },
        loop_status_deletions: #{ "type": "integer" },
        charters_ok: #{ "type": "boolean" },
        pytest_before: #{ "type": "string" },
        pytest_after: #{ "type": "string" },
        count_rose: #{ "type": "boolean" },
        ruff_ok: #{ "type": "boolean" },
        n_drift: #{ "type": "integer" },
        n_claims: #{ "type": "integer" },
        n_results_tracked: #{ "type": "integer" },
        evidence: #{ "type": "string" },
    },
};
let ci_schema = #{
    "type": "object",
    "required": ["ok", "pr_url", "pr_run_url", "main_run_url", "pr_lint", "pr_claim_audit", "pr_tests", "main_lint", "main_claim_audit", "main_tests", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        pr_url: #{ "type": "string" },
        pr_run_url: #{ "type": "string" },
        main_run_url: #{ "type": "string" },
        pr_lint: #{ "type": "string" },
        pr_claim_audit: #{ "type": "string" },
        pr_tests: #{ "type": "string" },
        main_lint: #{ "type": "string" },
        main_claim_audit: #{ "type": "string" },
        main_tests: #{ "type": "string" },
        evidence: #{ "type": "string" },
    },
};
let report_schema = #{
    "type": "object",
    "required": ["ok", "report_path", "multiplicity_statement", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        report_path: #{ "type": "string" },
        multiplicity_statement: #{ "type": "string" },
        evidence: #{ "type": "string" },
    },
};

let wt = if args == () { () } else { args.worktree };
let repo = if args == () { () } else { args.repo };
if wt == () || repo == () {
    pause("verification", "Pass args.worktree (multiday-screenfail) and args.repo");
}

let rules = "";
rules += "HARD: records-landing only — no screen, no null re-run, no retune, no revive, no sealed_cycle, ";
rules += "no backtest.py, no fetch_data, no Strategy Tester, no --live, no holdout peek. ";
rules += "Do NOT use git checkout --ours/--theirs on results/xau_loop_status.md — keep BOTH ";
rules += "2026-08-21 entries VERBATIM. Do NOT recompute K_prior or dead-family counts. ";
rules += "Do not refresh research_claim inventory or touch research_claim_selfref_allow.json. ";
rules += "Do not add numpy/pandas to pyproject.toml. Do not force-push main. Do not delete branches. ";
rules += "If a gate fails: report real output and STOP. Use tools; paste real evidence.\n";

// ---------------------------------------------------------------------------
phase("Prep");
let p0 = "";
p0 += rules;
p0 += "Worktree " + wt + " must be clean origin/main (research/xau-multiday-screenfail-land).\n";
p0 += "1) Confirm scripts/xau_family_null_maxstat.py unchanged on main since 41e8b3e:\n";
p0 += "   git diff --stat 41e8b3e..origin/main -- scripts/xau_family_null_maxstat.py  -> empty\n";
p0 += "2) Stale-doc trap in " + repo + ": five uncommitted docs. Diff each vs origin/main.\n";
p0 += "   Main should be superset for MCP/archive content (PR #47). Report any WT-unique content.\n";
p0 += "   Known: README wt may still have thesis row intentionally absent on main — report it.\n";
p0 += "   Do NOT carry those docs into this branch. stale_docs_safe=true only if nothing critical\n";
p0 += "   unique-to-wt must ride along (thesis row alone is OK to leave behind — say so).\n";
p0 += "   If WT has unique substance main lacks beyond the known skipped thesis row, set ok=false and stop.\n";
p0 += "evidence=paste diffs/summaries. null_maxstat_unchanged=true required.\n";
let prep = agent(p0, #{ label: "prep", capability_mode: "execute", cwd: wt, output_schema: prep_schema });
if prep == () || !prep.success || prep.output == () || prep.output.ok != true {
    complete(#{ ok: false, summary: "Prep failed / stop on stale docs", prep: prep });
}
if prep.output.null_maxstat_unchanged != true {
    complete(#{ ok: false, summary: "null_maxstat changed on main — stop", prep: prep.output });
}
log("Prep ok");

// ---------------------------------------------------------------------------
phase("CherryPick");
let p1 = "";
p1 += rules;
p1 += "In " + wt + " on research/xau-multiday-screenfail-land (from origin/main):\n";
p1 += "Cherry-pick BOTH commits in order (do not squash):\n";
p1 += "  d55064c  research(xau): freeze multi_day_variance_expansion_flat fixtures on HEAD\n";
p1 += "  70f0470  research(xau): record multi_day_variance_expansion_flat develop SCREEN_FAIL\n";
p1 += "Expect conflict ONLY in results/xau_loop_status.md.\n";
p1 += "RESOLVE by keeping BOTH 2026-08-21 entries in full (every field/table/SHA/metric):\n";
p1 += "  - branch: ## 2026-08-21 — Develop screen · multi_day_variance_expansion_flat SCREEN_FAIL\n";
p1 += "  - main:   ## 2026-08-21 — Consolidation · BACKTEST-RECORD\n";
p1 += "Also keep branch's 2026-08-20 freeze/fixture entries and all pre-existing main entries.\n";
p1 += "FORBIDDEN: git checkout --ours/--theirs for this file; dropping either entry.\n";
p1 += "Newest-first file. Same date — pick an order, preserve bodies verbatim, set order_chosen\n";
p1 += "and order_rationale (no intra-day timestamp evidence exists; state judgment).\n";
p1 += "Suggested rationale option: SCREEN_FAIL first as the look-consuming research event;\n";
p1 += "BACKTEST-RECORD second as same-day ledger consolidation — but you may choose the reverse\n";
p1 += "with stated reason. Land K_prior=11 / 11 dead families EXACTLY as in the SCREEN_FAIL entry.\n";
p1 += "After resolve: continue cherry-picks, commit resolution if needed. commit_shas=list.\n";
p1 += "ok=true only if both commits landed and both 2026-08-21 entries present verbatim.\n";
let cherry = agent(p1, #{ label: "cherry-pick-resolve", capability_mode: "all", cwd: wt, output_schema: cherry_schema });
if cherry == () || !cherry.success || cherry.output == () || cherry.output.ok != true {
    complete(#{ ok: false, summary: "CherryPick/conflict resolve failed", cherry: cherry });
}
log("CherryPick ok order=" + cherry.output.order_chosen);

// ---------------------------------------------------------------------------
phase("Gates");
let p2 = "";
p2 += rules;
p2 += "In " + wt + " run ALL gates; paste real output:\n";
p2 += "1) behind = git rev-list --count HEAD..origin/main  -> must be 0\n";
p2 += "2) d_lines = count of D lines in git diff --name-status origin/main...HEAD -> 0\n";
p2 += "3) holdout_identical: git diff origin/main -- results/xau_holdout_lock.json empty\n";
p2 += "4) loop_status_deletions: from git diff origin/main -- results/xau_loop_status.md\n";
p2 += "   count deleted lines (lines starting with - excluding ---). Must be 0 (additions only).\n";
p2 += "   Confirm both 2026-08-21 headings present.\n";
p2 += "5) charters_ok: new charter files are additions; registry jsonl gains exactly one appended line\n";
p2 += "   (not rewritten). Nothing under xau_charters/ or xau_runs/ deleted/modified unexpectedly.\n";
p2 += "6) pytest_before on origin/main tip (~796); pytest_after on HEAD (~811). count_rose=true required.\n";
p2 += "   uv run pytest -q -m 'not live'\n";
p2 += "7) uv run ruff check src tests -> ruff_ok\n";
p2 += "8) python3 scripts/research_claim_verify.py --fail-on-drift --out /tmp/multiday-claim.json\n";
p2 += "   n_drift must be 0. Report n_claims (expect flat ~531) and n_results_tracked (expect rise).\n";
p2 += "   Do NOT refresh inventory.\n";
p2 += "ok=true only if all numeric gates pass.\n";
let gates = agent(p2, #{ label: "gates", capability_mode: "execute", cwd: wt, output_schema: gates_schema });
if gates == () || !gates.success || gates.output == () || gates.output.ok != true {
    complete(#{ ok: false, summary: "Gates failed", gates: gates, cherry: cherry.output });
}
if gates.output.behind != 0 || gates.output.d_lines != 0 || gates.output.holdout_identical != true {
    complete(#{ ok: false, summary: "Structural gates failed", gates: gates.output });
}
if gates.output.loop_status_deletions != 0 || gates.output.count_rose != true || gates.output.n_drift != 0 {
    complete(#{ ok: false, summary: "loop_status/pytest/auditor gate failed", gates: gates.output });
}
log("Gates ok pytest " + gates.output.pytest_after);

// ---------------------------------------------------------------------------
phase("PRAndCI");
let p3 = "";
p3 += rules;
p3 += "Push research/xau-multiday-screenfail-land and open PR to main.\n";
p3 += "PR body MUST include: conflict resolution order (" + cherry.output.order_chosen + ") and rationale;\n";
p3 += "that both 2026-08-21 entries kept verbatim; K_prior not recomputed; this is records-landing\n";
p3 += "not research; promote=no / live_go=false; family not revived.\n";
p3 += "Wait for PR Actions — all three jobs success. Then merge.\n";
p3 += "Wait for SEPARATE main push run — all three success. Paste both URLs.\n";
p3 += "If tests flat/green without +~15, investigate — do not skip new tests.\n";
p3 += "ok=true only if pr_tests and main_tests are success.\n";
let ci = agent(p3, #{ label: "pr-ci", capability_mode: "all", cwd: wt, output_schema: ci_schema });
if ci == () || !ci.success || ci.output == () || ci.output.ok != true {
    complete(#{ ok: false, summary: "PR/CI failed", ci: ci, gates: gates.output });
}
if ci.output.pr_tests != "success" || ci.output.main_tests != "success" {
    complete(#{ ok: false, summary: "CI not green", ci: ci.output });
}
log("CI green " + ci.output.pr_url);

// ---------------------------------------------------------------------------
phase("Report");
let p4 = "";
p4 += rules;
p4 += "Write " + repo + "/scratchpad/multiday-screenfail-land-report.md with:\n";
p4 += "- PR number/URL; conflict order + rationale\n";
p4 += "- every gate with real numbers\n";
p4 += "- both Actions URLs with per-job conclusions\n";
p4 += "- MULTIPLICITY STATEMENT (required): what main now claims (K_prior/dead families from the\n";
p4 += "  landed SCREEN_FAIL entry), what looks are actually on record (incl. exog FAIL from #52),\n";
p4 += "  and what you believe the reconciled count should be. Do NOT edit loop_status to fix it.\n";
p4 += "- stale docs report; anything left undone\n";
p4 += "Data: prep=" + json_encode(prep.output) + " cherry=" + json_encode(cherry.output) + "\n";
p4 += "gates=" + json_encode(gates.output) + " ci=" + json_encode(ci.output) + "\n";
p4 += "multiplicity_statement=the statement. report_path=path. ok=true if written.\n";
let rep = agent(p4, #{ label: "report", capability_mode: "all", cwd: repo, output_schema: report_schema });
if rep == () || !rep.success || rep.output == () || rep.output.ok != true {
    complete(#{ ok: false, summary: "Report failed", report: rep });
}

let summary = "";
summary += "# multiday-screenfail-land\n\n";
summary += "- PR: " + ci.output.pr_url + "\n";
summary += "- order: " + cherry.output.order_chosen + "\n";
summary += "- PR run: " + ci.output.pr_run_url + "\n";
summary += "- main run: " + ci.output.main_run_url + "\n";
summary += "- report: " + rep.output.report_path + "\n";
let path = write_scratch_file("multiday-screenfail-land-summary.md", summary);
complete(#{
    ok: true,
    summary: "SCREEN_FAIL record landed with both loop_status entries",
    path: path,
    prep: prep.output,
    cherry: cherry.output,
    gates: gates.output,
    ci: ci.output,
    report: rep.output,
});
