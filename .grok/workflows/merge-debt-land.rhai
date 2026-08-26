let meta = #{
    name: "merge-debt-land",
    description: "Land claim-auditor merge debt: #42 -> auditor -> broker -> CI + hygiene",
    phases: [
        #{ title: "VerifyStart", detail: "reconfirm branch tips and stale-base facts" },
        #{ title: "Merge42", detail: "push observe-only fix; merge PR #42; ff local main" },
        #{ title: "LandAuditor", detail: "rebase audit; port --fail-on-drift; gates; open PR" },
        #{ title: "AwaitAuditorMerge", detail: "pause until auditor PR is on origin/main" },
        #{ title: "RecreateBroker", detail: "cherry-pick dc24d33 onto fresh main; assert gates; PR" },
        #{ title: "ResetCI", detail: "recreate PR #44 with only ci.yml; confirm Actions" },
        #{ title: "Hygiene", detail: "gitignore data; drop stale auditor copies; docs PR; prune" },
        #{ title: "Report", detail: "write per-step evidence report" },
    ],
};

let start_schema = #{
    "type": "object",
    "required": ["ok", "main_sha", "zacks_ahead", "zacks_behind", "audit_ahead", "audit_behind", "broker_behind", "ci_behind", "fail_on_drift_on_ci_only", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        main_sha: #{ "type": "string" },
        zacks_ahead: #{ "type": "integer" },
        zacks_behind: #{ "type": "integer" },
        audit_ahead: #{ "type": "integer" },
        audit_behind: #{ "type": "integer" },
        broker_behind: #{ "type": "integer" },
        ci_behind: #{ "type": "integer" },
        fail_on_drift_on_ci_only: #{ "type": "boolean" },
        evidence: #{ "type": "string" },
    },
};
let merge42_schema = #{
    "type": "object",
    "required": ["ok", "pushed_observe_only", "merged", "merge_sha", "main_ff_sha", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        pushed_observe_only: #{ "type": "boolean" },
        merged: #{ "type": "boolean" },
        merge_sha: #{ "type": "string" },
        main_ff_sha: #{ "type": "string" },
        evidence: #{ "type": "string" },
    },
};
let auditor_schema = #{
    "type": "object",
    "required": ["ok", "branch", "commit_sha", "pr_url", "n_claims", "n_drift", "mutant_caught", "controls_ok", "ruff_ok", "pytest_ok", "fail_on_drift_ported", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        branch: #{ "type": "string" },
        commit_sha: #{ "type": "string" },
        pr_url: #{ "type": "string" },
        n_claims: #{ "type": "integer" },
        n_drift: #{ "type": "integer" },
        mutant_caught: #{ "type": "boolean" },
        controls_ok: #{ "type": "boolean" },
        ruff_ok: #{ "type": "boolean" },
        pytest_ok: #{ "type": "boolean" },
        fail_on_drift_ported: #{ "type": "boolean" },
        evidence: #{ "type": "string" },
    },
};
let broker_schema = #{
    "type": "object",
    "required": ["ok", "branch", "commit_sha", "pr_url", "behind", "d_lines", "holdout_identical", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        branch: #{ "type": "string" },
        commit_sha: #{ "type": "string" },
        pr_url: #{ "type": "string" },
        behind: #{ "type": "integer" },
        d_lines: #{ "type": "integer" },
        holdout_identical: #{ "type": "boolean" },
        evidence: #{ "type": "string" },
    },
};
let ci_schema = #{
    "type": "object",
    "required": ["ok", "branch", "commit_sha", "pr_url", "actions_url", "actions_green", "only_ci_yml", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        branch: #{ "type": "string" },
        commit_sha: #{ "type": "string" },
        pr_url: #{ "type": "string" },
        actions_url: #{ "type": "string" },
        actions_green: #{ "type": "boolean" },
        only_ci_yml: #{ "type": "boolean" },
        evidence: #{ "type": "string" },
    },
};
let hygiene_schema = #{
    "type": "object",
    "required": ["ok", "gitignore_done", "stale_auditor_deleted", "docs_pr_url", "docs_pr_sha", "worktrees_pruned", "worktrees_left_dirty", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        gitignore_done: #{ "type": "boolean" },
        stale_auditor_deleted: #{ "type": "boolean" },
        docs_pr_url: #{ "type": "string" },
        docs_pr_sha: #{ "type": "string" },
        worktrees_pruned: #{ "type": "integer" },
        worktrees_left_dirty: #{ "type": "string" },
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
let audit_wt = if args == () { () } else { args.audit_wt };
let zacks_wt = if args == () { () } else { args.zacks_wt };
let broker_wt = if args == () { () } else { args.broker_wt };
let ci_wt = if args == () { () } else { args.ci_wt };
let merge_wt = if args == () { () } else { args.merge_wt };
if repo == () || audit_wt == () || zacks_wt == () || broker_wt == () || ci_wt == () || merge_wt == () {
    pause("verification", "Pass args.repo, args.audit_wt, args.zacks_wt, args.broker_wt, args.ci_wt, args.merge_wt");
}

let rules = "";
rules += "HARD: no --live; no holdout peek/fit; do not edit results/xau_loop_status.md; ";
rules += "do not add numpy/pandas to pyproject.toml; never print MT5_PASSWORD; ";
rules += "do not force-push main; force-push ONLY on ci/claim-audit-and-tests and ";
rules += "fix/broker-paths-and-instruction-drift (deliberate recreations). ";
rules += "If a gate fails: report real output and STOP that step — do not widen tolerance ";
rules += "or pad allowlists. Do not commit results/tick_data, eurusd_data, btc_data, or .crew. ";
rules += "Read AGENTS.md and CLAUDE.md; they override this prompt on conflict. ";
rules += "Use tools (shell/gh/git/read_file) — do not answer from memory.\n";

// ---------------------------------------------------------------------------
phase("VerifyStart");
let p0 = "";
p0 += rules;
p0 += "Repo root: " + repo + "\n";
p0 += "Re-verify starting state with real commands (git fetch origin main first):\n";
p0 += "1) origin/main SHA; tips of research/zacks-mcp-lane-2026-08, research/research-claim-audit,\n";
p0 += "   fix/broker-paths-and-instruction-drift, ci/claim-audit-and-tests with ahead/behind vs origin/main.\n";
p0 += "2) Confirm PR #44 illusion: git cat-file -e origin/main:scripts/eurusd_ny_scalp_core.py\n";
p0 += "   (and signal_edge_diagnostic.py, research_bias_gates.py, tests/test_eurusd_ny_scalp.py,\n";
p0 += "   docs/research/BACKTEST-RECORD.md) — all must exist on main.\n";
p0 += "3) Confirm --fail-on-drift only on CI branch: wc -l of research_claim_verify.py on\n";
p0 += "   ci-claim-audit vs research-claim-audit worktrees; rg fail-on-drift.\n";
p0 += "4) Confirm 196d8d3 is ancestor of both zacks and audit by SHA.\n";
p0 += "Set fail_on_drift_on_ci_only=true only if flag present on CI branch and absent on audit.\n";
p0 += "ok=true only if facts match the prompt's verified state (allow small SHA drift if main moved).\n";
p0 += "evidence must paste the real command outputs (ahead/behind counts, SHAs).\n";
let start = agent(p0, #{ label: "verify-start", capability_mode: "execute", cwd: repo, output_schema: start_schema });
if start == () || !start.success || start.output == () || start.output.ok != true {
    complete(#{ ok: false, summary: "VerifyStart failed — do not proceed", start: start });
}
if start.output.fail_on_drift_on_ci_only != true {
    complete(#{ ok: false, summary: "--fail-on-drift fact check failed", start: start.output });
}
log("VerifyStart ok main=" + start.output.main_sha);

// ---------------------------------------------------------------------------
phase("Merge42");
let p1 = "";
p1 += rules;
p1 += "Worktree: " + zacks_wt + " (branch research/zacks-mcp-lane-2026-08 = PR #42).\n";
p1 += "ORDERING STEP 1 — mandatory before auditor.\n";
p1 += "1) GATE before merge: read docs/README.md Zacks row and docs/research/ZACKS-MCP-OVERLAY-LANE.md.\n";
p1 += "   Remote origin still has **New edge:** — local tip b7c2cf6 fixes it to **Observe-only:**.\n";
p1 += "   Push the unpushed observe-only commit: git push origin research/zacks-mcp-lane-2026-08\n";
p1 += "   (ordinary push, NOT force). Confirm remote README no longer says New edge.\n";
p1 += "2) Confirm nothing claims promote/live-go/new edge. Then merge PR #42:\n";
p1 += "   gh pr merge 42 --repo Trujillofa/mt5-arch-integration --merge\n";
p1 += "3) git fetch origin; in a worktree that can update main (prefer " + merge_wt + " or\n";
p1 += "   mt5-arch-integration-wt-liq-sweep-fade which is on main), checkout main and\n";
p1 += "   git merge --ff-only origin/main. Local main was 34 behind — must fast-forward.\n";
p1 += "Do NOT edit research status. Return pushed_observe_only, merged, merge_sha, main_ff_sha.\n";
p1 += "ok=false if push or merge fails; paste gh/git output in evidence.\n";
let m42 = agent(p1, #{ label: "merge-42", capability_mode: "all", cwd: zacks_wt, output_schema: merge42_schema });
if m42 == () || !m42.success || m42.output == () || m42.output.ok != true {
    complete(#{ ok: false, summary: "Merge42 failed", merge42: m42 });
}
if m42.output.merged != true || m42.output.pushed_observe_only != true {
    complete(#{ ok: false, summary: "PR #42 not fully landed", merge42: m42.output });
}
log("Merge42 ok " + m42.output.merge_sha);

// ---------------------------------------------------------------------------
phase("LandAuditor");
let p2 = "";
p2 += rules;
p2 += "Worktree: " + audit_wt + " (branch research/research-claim-audit — NEVER PUSHED yet).\n";
p2 += "ORDERING STEP 2 — land the auditor (real deliverable).\n";
p2 += "1) git fetch origin. Rebase or merge origin/main so branch is 0 behind. Resolve conflicts\n";
p2 += "   carefully; do not drop verifier/mutant/instruction scripts or RESEARCH-CLAIM-AUDIT.md.\n";
p2 += "2) Port --fail-on-drift ONLY from " + ci_wt + "/scripts/research_claim_verify.py onto this\n";
p2 += "   branch's scripts/research_claim_verify.py. Diff the two files; apply ONLY the flag work:\n";
p2 += "   - argparse --fail-on-drift (default off)\n";
p2 += "   - write_inventory=not args.fail_on_drift (CI must not dirty the tree)\n";
p2 += "   - exit 1 when n_drift>0 or n_sha_unresolvable>0 or n_selfref_unallowlisted>0\n";
p2 += "   Do NOT change default exit semantics / report['ok'] meaning. Do not drag stale CI branch files.\n";
p2 += "3) Commit the port on this branch with a clear message.\n";
p2 += "4) Run FULL gates against post-#42 tree; paste REAL numbers in evidence:\n";
p2 += "   python3 scripts/research_claim_verify.py --out /tmp/merge-debt-claim.json\n";
p2 += "   python3 scripts/research_claim_mutant.py\n";
p2 += "   negative controls (same harness the auditor uses)\n";
p2 += "   uv run ruff check src tests\n";
p2 += "   uv run ruff check scripts/research_claim_verify.py scripts/research_claim_mutant.py scripts/research_claim_instruction.py\n";
p2 += "   uv run pytest -q -m 'not live'\n";
p2 += "5) Expect n_drift==0. If not, STOP and report drift items — do not widen tolerance or pad allowlist.\n";
p2 += "6) If main merge changed verifier search scope, re-derive results/research_claim_selfref_allow.json\n";
p2 += "   rather than hand-editing (standing rule from run 6).\n";
p2 += "7) Push branch (first push) and open PR with gh. PR body must say it supersedes the auditor half of #44.\n";
p2 += "Return n_claims, n_drift, mutant_caught, controls_ok, ruff_ok, pytest_ok, fail_on_drift_ported, pr_url, commit_sha.\n";
p2 += "ok=true only if n_drift==0 AND mutant_caught AND controls_ok AND ruff_ok AND pytest_ok AND fail_on_drift_ported AND pr_url non-empty.\n";
let aud = agent(p2, #{ label: "land-auditor", capability_mode: "all", cwd: audit_wt, output_schema: auditor_schema });
if aud == () || !aud.success || aud.output == () || aud.output.ok != true {
    complete(#{ ok: false, summary: "LandAuditor failed — stop; do not widen gates", auditor: aud });
}
if aud.output.n_drift != 0 {
    complete(#{ ok: false, summary: "n_drift != 0 after auditor land", auditor: aud.output });
}
log("LandAuditor PR " + aud.output.pr_url);

// ---------------------------------------------------------------------------
phase("AwaitAuditorMerge");
let await_msg = "";
await_msg += "Auditor PR opened: " + aud.output.pr_url + " (sha " + aud.output.commit_sha + "). ";
await_msg += "Merge it into main (required before CI reset). Then resume this workflow. ";
await_msg += "Do not recreate ci/claim-audit-and-tests until the auditor (with --fail-on-drift) is on origin/main.";
await_user("user", await_msg);

// Confirm merge happened before continuing
let p2b = "";
p2b += rules;
p2b += "Confirm the auditor PR is merged: git fetch origin; git cat-file -e origin/main:scripts/research_claim_verify.py;\n";
p2b += "rg -n fail-on-drift on origin/main:scripts/research_claim_verify.py must find the flag.\n";
p2b += "Also confirm RESEARCH-CLAIM-AUDIT.md and mutant/instruction scripts are on origin/main.\n";
p2b += "Set ok=true only if --fail-on-drift is on origin/main. evidence=paste proofs. ";
p2b += "n_claims/n_drift may be 0 here; set mutant_caught/controls/ruff/pytest from prior step if not re-run; ";
p2b += "fail_on_drift_ported=true; pr_url=" + aud.output.pr_url + "; branch=research/research-claim-audit; ";
p2b += "commit_sha=merged main tip or merge commit.\n";
let aud_merged = agent(p2b, #{ label: "confirm-auditor-merged", capability_mode: "execute", cwd: merge_wt, output_schema: auditor_schema });
if aud_merged == () || !aud_merged.success || aud_merged.output == () || aud_merged.output.ok != true {
    complete(#{ ok: false, summary: "Auditor not on origin/main yet — merge then resume", auditor_merge: aud_merged });
}
if aud_merged.output.fail_on_drift_ported != true {
    complete(#{ ok: false, summary: "--fail-on-drift still missing on origin/main", auditor_merge: aud_merged.output });
}
log("Auditor on main confirmed");

// ---------------------------------------------------------------------------
phase("RecreateBroker");
let p3 = "";
p3 += rules;
p3 += "ORDERING STEP 3 — recreate fix/broker-paths-and-instruction-drift from current origin/main.\n";
p3 += "Existing worktree: " + broker_wt + " is on stale tip dc24d33 (34 behind).\n";
p3 += "1) git fetch origin. Recreate branch from origin/main and cherry-pick dc24d33.\n";
p3 += "   Practical approach in the existing worktree:\n";
p3 += "   git checkout fix/broker-paths-and-instruction-drift\n";
p3 += "   git reset --hard origin/main\n";
p3 += "   git cherry-pick dc24d33\n";
p3 += "   Resolve conflicts WITHOUT accepting deletions of other people's merged work.\n";
p3 += "2) ASSERT and print evidence for EACH:\n";
p3 += "   a) git rev-list --count HEAD..origin/main == 0\n";
p3 += "   b) git diff --name-status origin/main...HEAD has ZERO lines starting with D\n";
p3 += "   c) git diff origin/main -- results/xau_holdout_lock.json is empty (byte-identical)\n";
p3 += "   d) nothing under results/xau_charters/ or results/xau_runs/ modified/deleted\n";
p3 += "3) Force-push the recreated branch (allowed): git push --force-with-lease origin HEAD:fix/broker-paths-and-instruction-drift\n";
p3 += "4) Open a PR (or update existing if any). Return behind, d_lines, holdout_identical, pr_url, commit_sha.\n";
p3 += "ok=true only if behind==0 AND d_lines==0 AND holdout_identical==true AND pr opened.\n";
p3 += "If any assertion fails, STOP — that is the stale-base failure mode.\n";
let bro = agent(p3, #{ label: "recreate-broker", capability_mode: "all", cwd: broker_wt, output_schema: broker_schema });
if bro == () || !bro.success || bro.output == () || bro.output.ok != true {
    complete(#{ ok: false, summary: "RecreateBroker failed", broker: bro });
}
if bro.output.behind != 0 || bro.output.d_lines != 0 || bro.output.holdout_identical != true {
    complete(#{ ok: false, summary: "Broker recreate gates failed", broker: bro.output });
}
log("Broker PR " + bro.output.pr_url);

// ---------------------------------------------------------------------------
phase("ResetCI");
let p4 = "";
p4 += rules;
p4 += "ORDERING STEP 4 — reset PR #44 to ONLY .github/workflows/ci.yml after auditor is on main.\n";
p4 += "Worktree: " + ci_wt + " (branch ci/claim-audit-and-tests).\n";
p4 += "1) git fetch origin. Recreate from origin/main carrying ONLY .github/workflows/ci.yml:\n";
p4 += "   Save the ci.yml content from current branch first (read the file).\n";
p4 += "   git reset --hard origin/main\n";
p4 += "   Restore ONLY .github/workflows/ci.yml (mkdir -p .github/workflows; write file).\n";
p4 += "   Commit. Diff vs origin/main must be that single file.\n";
p4 += "2) Sanity-check layering in ci.yml before push:\n";
p4 += "   - claim-audit job: stdlib-only, no uv sync, no numpy/pandas\n";
p4 += "   - tests job: uv pip install numpy pandas (NOT in pyproject.toml)\n";
p4 += "   - no screens/backtests/fetch_data/live_trader/Wine/secrets\n";
p4 += "3) Force-push with lease so PR #44 updates in place:\n";
p4 += "   git push --force-with-lease origin HEAD:ci/claim-audit-and-tests\n";
p4 += "4) Wait for GitHub Actions on PR #44; paste run URL. Set actions_green from real status.\n";
p4 += "   If tests fail, report — do not skip tests. xauusd_data.csv IS tracked on main.\n";
p4 += "only_ci_yml=true only if git diff --name-only origin/main...HEAD is exactly .github/workflows/ci.yml.\n";
p4 += "ok=true only if only_ci_yml and push succeeded; actions_green should reflect real CI (prefer true).\n";
let ci = agent(p4, #{ label: "reset-ci", capability_mode: "all", cwd: ci_wt, output_schema: ci_schema });
if ci == () || !ci.success || ci.output == () || ci.output.ok != true {
    complete(#{ ok: false, summary: "ResetCI failed", ci: ci });
}
if ci.output.only_ci_yml != true {
    complete(#{ ok: false, summary: "CI branch is not ci.yml-only", ci: ci.output });
}
log("CI PR " + ci.output.pr_url + " actions=" + ci.output.actions_url);

// ---------------------------------------------------------------------------
phase("Hygiene");
let p5 = "";
p5 += rules;
p5 += "ORDERING STEP 5 — working-tree hygiene. Main checkout: " + repo + "\n";
p5 += "Orchestration/docs worktree (clean origin/main base): " + merge_wt + " on chore/merge-debt-land.\n";
p5 += "5.1 Gitignore large untracked data in " + repo + " — add to .gitignore (same spirit as existing):\n";
p5 += "    results/tick_data/ results/eurusd_data/ results/btc_data/ .crew/ pi-session-*.html\n";
p5 += "    Commit on an appropriate branch off main (use " + merge_wt + " / chore/merge-debt-land or a docs branch).\n";
p5 += "    Do NOT commit the data itself.\n";
p5 += "5.2 Delete stale untracked auditor copies in " + repo + " ONLY after confirming they match audit\n";
p5 += "    branch content or are older (frozen at 52c6baf). Files:\n";
p5 += "    scripts/research_claim_verify.py, research_claim_instruction.py, research_claim_mutant.py,\n";
p5 += "    results/research_claim_negative_controls.json. Do not delete anything newer than audit tip.\n";
p5 += "5.3 Docs PR off current origin/main in " + merge_wt + ":\n";
p5 += "    - docs/HOWTO-MT5-AI-MCP.md: replace published LAN URL http://192.168.0.144:22346/mcp with\n";
p5 += "      verified 127.0.0.1:22346 bind guidance; tell reader to take URL from ss / scripts/21-official-mcp-status.sh\n";
p5 += "    - Archive US-index 1%/20% goal in HOWTO-US-INDEX-SCALP.md, MT5-INTEGRATION-CAPABILITIES.md,\n";
p5 += "      docs/README.md, docs/research/US-INDEX-SESSION-SCALP-DESIGN.md (observe-only overlay).\n";
p5 += "    BLOCKER: also commit results/us_index_session_goal_archived.md in the SAME PR or links dangle.\n";
p5 += "    Source that file from " + repo + "/results/us_index_session_goal_archived.md (currently untracked).\n";
p5 += "    Re-apply edits onto current origin/main — do not copy stale working-tree blobs wholesale.\n";
p5 += "    Before adding README row for XAU-THESIS-multi_day_variance_expansion_flat_v1.md, confirm it exists on main.\n";
p5 += "    Push and open docs PR; return docs_pr_url and docs_pr_sha.\n";
p5 += "5.4 Prune merged worktrees (0 ahead of main). Check each is clean first; if dirty, leave and list in\n";
p5 += "    worktrees_left_dirty. Candidates: force-login-prefix, hyprland-056, official-mcp-wine, mcp-env-setup,\n";
p5 += "    hygiene-charter-ruff, mcp-fadd, eurusd-fixes, signal-triage, record-bias-gates, exog-phase-e.\n";
p5 += "    Leave simulator-conformance and exog-daily-paper-gate alone (unmerged commits).\n";
p5 += "    Also leave zacks/audit/broker/ci/merge-debt worktrees alone.\n";
p5 += "ok=true if gitignore_done and docs PR opened with archived note included; stale deletes may be partial if newer.\n";
let hyg = agent(p5, #{ label: "hygiene", capability_mode: "all", cwd: merge_wt, output_schema: hygiene_schema });
if hyg == () || !hyg.success || hyg.output == () || hyg.output.ok != true {
    complete(#{ ok: false, summary: "Hygiene failed", hygiene: hyg, prior: #{ auditor: aud.output, broker: bro.output, ci: ci.output } });
}
log("Hygiene docs PR " + hyg.output.docs_pr_url);

// ---------------------------------------------------------------------------
phase("Report");
let p6 = "";
p6 += rules;
p6 += "Write scratchpad/merge-debt-land-report.md in " + merge_wt + " (or " + repo + "/scratchpad/) summarizing all five steps.\n";
p6 += "Include REAL gate numbers and URLs from prior phases — do not invent.\n";
p6 += "Known prior outputs to incorporate (verify still current with quick git/gh checks):\n";
p6 += "Merge42: " + json_encode(m42.output) + "\n";
p6 += "Auditor: " + json_encode(aud.output) + "\n";
p6 += "Broker: " + json_encode(bro.output) + "\n";
p6 += "CI: " + json_encode(ci.output) + "\n";
p6 += "Hygiene: " + json_encode(hyg.output) + "\n";
p6 += "State explicitly anything left undone and why. report_path = path written. ok=true if report written.\n";
let rep = agent(p6, #{ label: "report", capability_mode: "all", cwd: merge_wt, output_schema: report_schema });
if rep == () || !rep.success || rep.output == () || rep.output.ok != true {
    complete(#{ ok: false, summary: "Report phase failed", report: rep });
}

let summary = "";
summary += "# merge-debt-land result\n\n";
summary += "- VerifyStart: ok main=" + start.output.main_sha + "\n";
summary += "- Merge42: " + m42.output.merge_sha + "\n";
summary += "- Auditor PR: " + aud.output.pr_url + " n_drift=" + aud.output.n_drift.to_string() + "\n";
summary += "- Broker PR: " + bro.output.pr_url + " behind=" + bro.output.behind.to_string() + " D=" + bro.output.d_lines.to_string() + "\n";
summary += "- CI PR: " + ci.output.pr_url + " actions=" + ci.output.actions_url + "\n";
summary += "- Docs/hygiene PR: " + hyg.output.docs_pr_url + "\n";
summary += "- Report: " + rep.output.report_path + "\n";

let path = write_scratch_file("merge-debt-land-summary.md", summary);
complete(#{
    ok: true,
    summary: "merge debt land pipeline finished",
    path: path,
    merge42: m42.output,
    auditor: aud.output,
    broker: bro.output,
    ci: ci.output,
    hygiene: hyg.output,
    report: rep.output,
});
