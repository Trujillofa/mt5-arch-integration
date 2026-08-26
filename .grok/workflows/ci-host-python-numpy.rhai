let meta = #{
    name: "ci-host-python-numpy",
    description: "Fix red CI tests job (host-python numpy gap) + close merge-debt leftovers",
    phases: [
        #{ title: "Diagnose", detail: "re-query Actions; confirm root cause from failed logs" },
        #{ title: "Fix", detail: "Half A ci.yml system pip + Half B skip-when-no-host-pandas" },
        #{ title: "VerifyLocal", detail: "pytest pass locally; prove skip path; no pyproject deps" },
        #{ title: "PRAndCI", detail: "open PR; wait for green Actions; merge; confirm main push run" },
        #{ title: "Leftovers", detail: "delete stale neg-controls; report dirty/unmerged; n_drift" },
        #{ title: "Report", detail: "write report with run URLs and keep/close recs" },
    ],
};

let diag_schema = #{
    "type": "object",
    "required": ["ok", "actions_enabled", "runs_total", "tests_only_red", "root_cause", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        actions_enabled: #{ "type": "boolean" },
        runs_total: #{ "type": "integer" },
        tests_only_red: #{ "type": "boolean" },
        root_cause: #{ "type": "string" },
        evidence: #{ "type": "string" },
    },
};
let fix_schema = #{
    "type": "object",
    "required": ["ok", "half_a", "half_b", "break_system_packages_used", "commit_sha", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        half_a: #{ "type": "boolean" },
        half_b: #{ "type": "boolean" },
        break_system_packages_used: #{ "type": "boolean" },
        commit_sha: #{ "type": "string" },
        evidence: #{ "type": "string" },
    },
};
let local_schema = #{
    "type": "object",
    "required": ["ok", "pytest_pass_count", "pytest_fail_count", "skip_proof", "pyproject_clean", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        pytest_pass_count: #{ "type": "integer" },
        pytest_fail_count: #{ "type": "integer" },
        skip_proof: #{ "type": "boolean" },
        pyproject_clean: #{ "type": "boolean" },
        evidence: #{ "type": "string" },
    },
};
let ci_schema = #{
    "type": "object",
    "required": ["ok", "pr_url", "pr_run_url", "pr_lint", "pr_claim_audit", "pr_tests", "main_run_url", "main_lint", "main_claim_audit", "main_tests", "n_drift", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        pr_url: #{ "type": "string" },
        pr_run_url: #{ "type": "string" },
        pr_lint: #{ "type": "string" },
        pr_claim_audit: #{ "type": "string" },
        pr_tests: #{ "type": "string" },
        main_run_url: #{ "type": "string" },
        main_lint: #{ "type": "string" },
        main_claim_audit: #{ "type": "string" },
        main_tests: #{ "type": "string" },
        n_drift: #{ "type": "integer" },
        evidence: #{ "type": "string" },
    },
};
let left_schema = #{
    "type": "object",
    "required": ["ok", "neg_controls_deleted", "signal_triage_summary", "simulator_rec", "exog_rec", "thesis_row_skipped", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        neg_controls_deleted: #{ "type": "boolean" },
        signal_triage_summary: #{ "type": "string" },
        simulator_rec: #{ "type": "string" },
        exog_rec: #{ "type": "string" },
        thesis_row_skipped: #{ "type": "boolean" },
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

let wt = if args == () { () } else { args.worktree };
let repo = if args == () { () } else { args.repo };
if wt == () || repo == () {
    pause("verification", "Pass args.worktree (fix/ci-host-python-numpy) and args.repo (main checkout)");
}

let rules = "";
rules += "HARD: do not add numpy/pandas to pyproject.toml; claim-audit stays stdlib-only; ";
rules += "no --live; no holdout peek; do not edit results/xau_loop_status.md; ";
rules += "do not force-push main; do not merge/force-push/delete simulator-conformance or ";
rules += "exog-fx-daily-cosign-xau-paper-gate; do not discard signal-triage dirty work yourself. ";
rules += "Skip-guard-only is NOT acceptable — Half A (system pip) is required so SCREEN_FAIL ";
rules += "assertions still execute in CI. Keep assert ModuleNotFoundError not in blob. ";
rules += "Paste REAL gh run URLs and job conclusions — never close a PR on local-only evidence. ";
rules += "Re-query Actions before concluding it has not run. Use tools; do not answer from memory.\n";

// ---------------------------------------------------------------------------
phase("Diagnose");
let p0 = "";
p0 += rules;
p0 += "Work in " + wt + " (branch fix/ci-host-python-numpy from origin/main).\n";
p0 += "1) Re-query Actions (do NOT trust a stale total_count=0):\n";
p0 += "   gh api repos/Trujillofa/mt5-arch-integration/actions/permissions\n";
p0 += "   gh api repos/Trujillofa/mt5-arch-integration/actions/workflows\n";
p0 += "   gh api 'repos/Trujillofa/mt5-arch-integration/actions/runs?per_page=10'\n";
p0 += "   gh run list --workflow ci.yml --limit 8\n";
p0 += "2) For the latest failed main push run, gh run view <id> --log-failed and confirm:\n";
p0 += "   lint=success, claim-audit=success, tests=failure; only the two joint_london tests fail\n";
p0 += "   with ModuleNotFoundError: numpy inside subprocess (SCREEN_FAIL assertion sees traceback).\n";
p0 += "3) Read tests/test_joint_london_open_cosign_fade_freeze.py::_host_python_and_env (~306)\n";
p0 += "   and .github/workflows/ci.yml tests job (~85). Confirm uv pip cannot fix host escape.\n";
p0 += "Set actions_enabled, runs_total (>=5), tests_only_red=true, root_cause brief string.\n";
p0 += "ok=true only if diagnosis matches. evidence=paste commands+outputs.\n";
let diag = agent(p0, #{ label: "diagnose", capability_mode: "execute", cwd: wt, output_schema: diag_schema });
if diag == () || !diag.success || diag.output == () || diag.output.ok != true {
    complete(#{ ok: false, summary: "Diagnose failed", diagnose: diag });
}
if diag.output.tests_only_red != true || diag.output.actions_enabled != true {
    complete(#{ ok: false, summary: "Unexpected CI state — stop", diagnose: diag.output });
}
log("Diagnose ok runs_total=" + diag.output.runs_total.to_string());

// ---------------------------------------------------------------------------
phase("Fix");
let p1 = "";
p1 += rules;
p1 += "Work ONLY in " + wt + " on fix/ci-host-python-numpy.\n";
p1 += "HALF A — .github/workflows/ci.yml tests job only. Extend Install research test deps:\n";
p1 += "  uv pip install numpy pandas\n";
p1 += "  THEN also install into system python3. First try WITHOUT --break-system-packages:\n";
p1 += "    python3 -m pip install numpy pandas\n";
p1 += "  If docs/runner need the flag, use --break-system-packages and set break_system_packages_used=true.\n";
p1 += "  Prefer dropping the flag if unneeded. Do not touch lint or claim-audit jobs.\n";
p1 += "HALF B — tests/test_joint_london_open_cosign_fade_freeze.py:\n";
p1 += "  Change _host_python_and_env to return Optional — None (or (None, env)) when no candidate\n";
p1 += "  can import pandas; do NOT fall back to a proven-broken /usr/bin/python3.\n";
p1 += "  Both tests at ~341 and ~366: if no host python, pytest.skip with a message naming the gap.\n";
p1 += "  Keep all SCREEN_FAIL / ModuleNotFoundError-not-in-blob assertions when python is found.\n";
p1 += "  Leave or lightly generalise /home/yderf/bin/python3 candidate — do not make it the only path.\n";
p1 += "Commit both halves. half_a=true half_b=true. commit_sha=HEAD. ok=false if either half missing.\n";
let fix = agent(p1, #{ label: "fix-both-halves", capability_mode: "all", cwd: wt, output_schema: fix_schema });
if fix == () || !fix.success || fix.output == () || fix.output.ok != true {
    complete(#{ ok: false, summary: "Fix failed", fix: fix });
}
if fix.output.half_a != true || fix.output.half_b != true {
    complete(#{ ok: false, summary: "Incomplete fix — skip-guard-only forbidden", fix: fix.output });
}
log("Fix committed " + fix.output.commit_sha);

// ---------------------------------------------------------------------------
phase("VerifyLocal");
let p2 = "";
p2 += rules;
p2 += "In " + wt + ":\n";
p2 += "1) uv run pytest -q -m 'not live' — the two joint_london tests must RUN and PASS.\n";
p2 += "   Report pass/fail counts (expect ~781 passed locally).\n";
p2 += "2) Prove Half B skip: temporarily make no candidate import pandas (e.g. monkeypatch via\n";
p2 += "   running pytest with a wrapper, or briefly edit candidates to only a bare python then revert).\n";
p2 += "   Show the two tests SKIP rather than FAIL. Revert scaffolding afterwards.\n";
p2 += "3) Confirm pyproject.toml still has no numpy/pandas dependency lines (pyproject_clean=true).\n";
p2 += "ok=true only if pytest_fail_count==0 and skip_proof and pyproject_clean. evidence=paste output.\n";
let loc = agent(p2, #{ label: "verify-local", capability_mode: "all", cwd: wt, output_schema: local_schema });
if loc == () || !loc.success || loc.output == () || loc.output.ok != true {
    complete(#{ ok: false, summary: "VerifyLocal failed", local: loc });
}
if loc.output.pytest_fail_count != 0 || loc.output.skip_proof != true || loc.output.pyproject_clean != true {
    complete(#{ ok: false, summary: "Local gates not met", local: loc.output });
}
log("VerifyLocal ok passes=" + loc.output.pytest_pass_count.to_string());

// ---------------------------------------------------------------------------
phase("PRAndCI");
let p3 = "";
p3 += rules;
p3 += "In " + wt + ":\n";
p3 += "1) Push fix/ci-host-python-numpy and open a PR to main. Body must state both halves and\n";
p3 += "   that skip-guard-only was rejected; cite failed run 32990178881 as motivation.\n";
p3 += "2) Wait for the PR's Actions run. Use gh run list / gh pr checks. If red:\n";
p3 += "   gh run view <id> --log-failed — fix and push; do not declare green from local only.\n";
p3 += "3) When PR lint+claim-audit+tests are all success, merge the PR.\n";
p3 += "4) Wait for the SEPARATE push run on main. Paste main_run_url and per-job conclusions.\n";
p3 += "   A green PR run alone is NOT enough.\n";
p3 += "5) Post-merge: python3 scripts/research_claim_verify.py --out /tmp/ci-red-claim.json\n";
p3 += "   Record n_drift. If n_drift!=0, set ok=false and stop — do not widen allowlist.\n";
p3 += "ok=true only if pr_tests==success AND main_tests==success AND n_drift==0.\n";
p3 += "Job conclusion fields must be exact strings: success|failure|cancelled|skipped.\n";
let ci = agent(p3, #{ label: "pr-and-ci", capability_mode: "all", cwd: wt, output_schema: ci_schema });
if ci == () || !ci.success || ci.output == () || ci.output.ok != true {
    complete(#{ ok: false, summary: "PR/CI failed — stop", ci: ci });
}
if ci.output.pr_tests != "success" || ci.output.main_tests != "success" || ci.output.n_drift != 0 {
    complete(#{ ok: false, summary: "CI or n_drift gate failed", ci: ci.output });
}
log("CI green PR=" + ci.output.pr_run_url + " main=" + ci.output.main_run_url);

// ---------------------------------------------------------------------------
phase("Leftovers");
let p4 = "";
p4 += rules;
p4 += "Main research checkout: " + repo + "\n";
p4 += "6) Confirm origin/main has results/research_claim_negative_controls.json (git cat-file -e).\n";
p4 += "   Then delete the UNTRACKED copy at " + repo + "/results/research_claim_negative_controls.json\n";
p4 += "   if present. neg_controls_deleted=true only if deleted or already absent after confirm.\n";
p4 += "7) signal-triage worktree at .../signal-triage: git status + diffstat. Summarise uncommitted\n";
p4 += "   work in signal_triage_summary. Do NOT discard.\n";
p4 += "8) research/simulator-conformance and research/exog-fx-daily-cosign-xau-paper-gate:\n";
p4 += "   summarise commits ahead of main; recommend keep or close (landable / mergeable-as-is /\n";
p4 += "   research-red). Do NOT merge, force-push, or delete. Put rec in simulator_rec and exog_rec.\n";
p4 += "9) thesis_row_skipped=true — file still not on main; leave README row skipped.\n";
p4 += "ok=true if leftovers reported; evidence=paste status/diffstat/log --oneline snippets.\n";
let left = agent(p4, #{ label: "leftovers", capability_mode: "all", cwd: repo, output_schema: left_schema });
if left == () || !left.success || left.output == () || left.output.ok != true {
    complete(#{ ok: false, summary: "Leftovers phase failed", leftovers: left, ci: ci.output });
}
log("Leftovers done");

// ---------------------------------------------------------------------------
phase("Report");
let p5 = "";
p5 += rules;
p5 += "Write " + repo + "/scratchpad/ci-host-python-numpy-report.md with:\n";
p5 += "- Corrections 1–2 acknowledged (Actions was running; tests-only red)\n";
p5 += "- Fix landed (both halves, break_system_packages decision)\n";
p5 += "- PR URL + PR run URL + main push run URL with per-job conclusions\n";
p5 += "- Local pytest counts + skip proof\n";
p5 += "- post-merge n_drift\n";
p5 += "- leftovers: neg delete, signal-triage contents, keep/close for two branches, thesis skipped\n";
p5 += "- anything left undone\n";
p5 += "Prior JSON to incorporate: fix=" + json_encode(fix.output) + " local=" + json_encode(loc.output) + "\n";
p5 += "ci=" + json_encode(ci.output) + " leftovers=" + json_encode(left.output) + "\n";
p5 += "report_path=that path. ok=true if written.\n";
let rep = agent(p5, #{ label: "report", capability_mode: "all", cwd: repo, output_schema: report_schema });
if rep == () || !rep.success || rep.output == () || rep.output.ok != true {
    complete(#{ ok: false, summary: "Report failed", report: rep });
}

let summary = "";
summary += "# ci-host-python-numpy\n\n";
summary += "- PR: " + ci.output.pr_url + "\n";
summary += "- PR run: " + ci.output.pr_run_url + " tests=" + ci.output.pr_tests + "\n";
summary += "- main run: " + ci.output.main_run_url + " tests=" + ci.output.main_tests + "\n";
summary += "- n_drift: " + ci.output.n_drift.to_string() + "\n";
summary += "- report: " + rep.output.report_path + "\n";
let path = write_scratch_file("ci-host-python-numpy-summary.md", summary);
complete(#{
    ok: true,
    summary: "CI host-python numpy gap fixed; leftovers reported",
    path: path,
    diagnose: diag.output,
    fix: fix.output,
    local: loc.output,
    ci: ci.output,
    leftovers: left.output,
    report: rep.output,
});
