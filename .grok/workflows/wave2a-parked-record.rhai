let meta = #{
    name: "wave2a-parked-record",
    description: "Land Wave 2A parked doc + evidence; fix stale study claims; do not run evaluator",
    phases: [
        #{ title: "Prep", detail: "base 2968d26; hash artifact; confirm ledger absent; #63 no selection change" },
        #{ title: "Record", detail: "commit evidence; write parked.md; split stale study/holdout claims" },
        #{ title: "Gates", detail: "diff shape; JSON hash; numbers from JSON; greps; ruff/mypy/pytest" },
        #{ title: "OpenPR", detail: "push + open PR; await human before merge" },
        #{ title: "MergeCI", detail: "merge after resume; green PR+main push runs" },
        #{ title: "Report", detail: "URLs; holdout still unspent; leftovers" },
    ],
};

let prep_schema = #{
    "type": "object",
    "required": ["ok", "main_sha", "artifact_sha256", "ledger_absent", "pr63_safe", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        main_sha: #{ "type": "string" },
        artifact_sha256: #{ "type": "string" },
        ledger_absent: #{ "type": "boolean" },
        pr63_safe: #{ "type": "boolean" },
        evidence: #{ "type": "string" },
    },
};
let record_schema = #{
    "type": "object",
    "required": ["ok", "parked_path", "stale_edits", "pythonpath_noted", "prohibition_stated", "commit_sha", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        parked_path: #{ "type": "string" },
        stale_edits: #{ "type": "string" },
        pythonpath_noted: #{ "type": "boolean" },
        prohibition_stated: #{ "type": "boolean" },
        commit_sha: #{ "type": "string" },
        evidence: #{ "type": "string" },
    },
};
let gates_schema = #{
    "type": "object",
    "required": ["ok", "d_lines", "log_not_committed", "json_hash_match", "numbers_from_json", "study_claims_gone", "holdout_claims_remain", "ruff_ok", "mypy_ok", "pytest_ok", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        d_lines: #{ "type": "integer" },
        log_not_committed: #{ "type": "boolean" },
        json_hash_match: #{ "type": "boolean" },
        numbers_from_json: #{ "type": "boolean" },
        study_claims_gone: #{ "type": "boolean" },
        holdout_claims_remain: #{ "type": "boolean" },
        ruff_ok: #{ "type": "boolean" },
        mypy_ok: #{ "type": "boolean" },
        pytest_ok: #{ "type": "boolean" },
        evidence: #{ "type": "string" },
    },
};
let pr_schema = #{
    "type": "object",
    "required": ["ok", "pr_url", "pr_number", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        pr_url: #{ "type": "string" },
        pr_number: #{ "type": "integer" },
        evidence: #{ "type": "string" },
    },
};
let ci_schema = #{
    "type": "object",
    "required": ["ok", "pr_run_url", "main_run_url", "pr_jobs", "main_jobs", "ledger_still_absent", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        pr_run_url: #{ "type": "string" },
        main_run_url: #{ "type": "string" },
        pr_jobs: #{ "type": "string" },
        main_jobs: #{ "type": "string" },
        ledger_still_absent: #{ "type": "boolean" },
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
let artifact_src = if args == () { () } else { args.artifact_src };
if wt == () || repo == () || artifact_src == () {
    pause("verification", "Pass args.worktree, args.repo, args.artifact_src (path to data/wave2a with JSON+PREREG)");
}

let rules = "";
rules += "HARD: Do NOT run the evaluator — not synthetic, not real, not 'to confirm'. ";
rules += "Do not create/move/delete any holdout ledger or canonical ledger directory. ";
rules += "Do not modify or commit the 26MB CSV. Do not edit PREREGISTRATION.md. ";
rules += "Do not change settings.yaml, src/cli.py, live/paper, gates, thresholds, costs, GARCH, production. ";
rules += "Do not force-push main. Do not retro-edit PREREGISTRATION.md. ";
rules += "Leave docs/plans/branch-merge-plan.md untracked if present in main checkout. ";
rules += "Every metric in the parked doc MUST be read from the study JSON — not transcribed from the prompt. ";
rules += "Write the retune prohibition as a prohibition, not a footnote. Use tools.\n";

// ---------------------------------------------------------------------------
phase("Prep");
let p0 = "";
p0 += rules;
p0 += "Worktree " + wt + " must be docs/wave2a-low-vol-veto-parked @ origin/main 2968d26.\n";
p0 += "1) Confirm HEAD == origin/main == 2968d26 (PR #63 merge).\n";
p0 += "2) Hash artifact BEFORE copy: sha256sum " + artifact_src + "/wave2a_fixed_low_vol_veto_v1_study.json\n";
p0 += "   Record artifact_sha256. Confirm source_sha inside JSON is 074f843… (study ran there).\n";
p0 += "3) Confirm canonical holdout ledger directory ABSENT on this machine for this data SHA\n";
p0 += "   (path pattern under ~/.local/state/ctrader-trading-agent/research/wave2a_holdout/…).\n";
p0 += "   ledger_absent=true required. Do not create it.\n";
p0 += "4) Confirm PR #63 (cfea108) only hardens ledger claim OS errors — no gate/selection/path change\n";
p0 += "   that would invalidate the study. pr63_safe=true. State study stands at 074f843, not 2968d26.\n";
p0 += "ok=true with evidence pasted.\n";
let prep = agent(p0, #{ label: "prep", capability_mode: "execute", cwd: wt, output_schema: prep_schema });
if prep == () || !prep.success || prep.output == () || prep.output.ok != true {
    complete(#{ ok: false, summary: "Prep failed", prep: prep });
}
if prep.output.ledger_absent != true || prep.output.pr63_safe != true {
    complete(#{ ok: false, summary: "Ledger present or PR63 unsafe — stop", prep: prep.output });
}
log("Prep ok artifact=" + prep.output.artifact_sha256);

// ---------------------------------------------------------------------------
phase("Record");
let p1 = "";
p1 += rules;
p1 += "In " + wt + ":\n";
p1 += "1) mkdir -p data/wave2a. Copy ONLY:\n";
p1 += "   " + artifact_src + "/PREREGISTRATION.md\n";
p1 += "   " + artifact_src + "/wave2a_fixed_low_vol_veto_v1_study.json\n";
p1 += "   Do NOT copy study_run.log. After copy, sha256sum the JSON and confirm it matches prep hash.\n";
p1 += "2) Create docs/wave2a-low-vol-veto-parked.md mirroring docs/garch-wave1-parked.md structure:\n";
p1 += "   # title — PARKED; lead note CSV not in git; Decision; Preregistration; Frozen command;\n";
p1 += "   Outcome; What this does not authorize.\n";
p1 += "   Distinction: Wave 1 failed closed; Wave 2A parked on develop, holdout unopened & available\n";
p1 += "   for a DIFFERENT candidate — NOT for a retuned version of this veto (quantile/lookback/ddof/\n";
p1 += "   thresholds/gates). Write that as an explicit prohibition.\n";
p1 += "   Record PYTHONPATH pin to study worktree honestly; do not normalise away.\n";
p1 += "   Note main advanced to 2968d26 via #63 without changing selection/gates — study SHA remains 074f843.\n";
p1 += "   READ EVERY NUMBER from the JSON file (decision, metrics table, veto counts, data identity).\n";
p1 += "3) Fix stale claims — SPLIT study vs holdout halves:\n";
p1 += "   docs/BACKTESTING.md:~102\n";
p1 += "   docs/wave2a-low-vol-veto-charter.md:~5 and ~211-212 (check ~248 leave if correct)\n";
p1 += "   Link parked.md from BACKTESTING like garch-wave1-parked at :23 and :41.\n";
p1 += "4) Commit. Do not edit PREREGISTRATION.md contents. prohibition_stated=true required.\n";
p1 += "pythonpath_noted=true required. parked_path=docs/wave2a-low-vol-veto-parked.md.\n";
let rec = agent(p1, #{ label: "record", capability_mode: "all", cwd: wt, output_schema: record_schema });
if rec == () || !rec.success || rec.output == () || rec.output.ok != true {
    complete(#{ ok: false, summary: "Record phase failed", record: rec });
}
if rec.output.prohibition_stated != true || rec.output.pythonpath_noted != true {
    complete(#{ ok: false, summary: "Missing prohibition or PYTHONPATH note", record: rec.output });
}
log("Record ok " + rec.output.commit_sha);

// ---------------------------------------------------------------------------
phase("Gates");
let p2 = "";
p2 += rules;
p2 += "Gates — paste real output:\n";
p2 += "1) git diff --name-status origin/main...HEAD — only new parked doc, corrected docs,\n";
p2 += "   PREREGISTRATION.md, study JSON. d_lines=0.\n";
p2 += "2) study_run.log NOT committed (check-ignore and absence from diff). log_not_committed=true.\n";
p2 += "3) sha256sum of committed JSON == prep artifact_sha256 (" + prep.output.artifact_sha256 + ").\n";
p2 += "4) numbers_from_json=true — show you read decision/metrics/veto counts from the JSON into the doc\n";
p2 += "   (diff key figures against json.load).\n";
p2 += "5) Grep: zero remaining claims that the *study* has not been run; holdout prohibitions remain.\n";
p2 += "6) Repo's usual checks: ruff check src/ tests/; ruff check scripts/backtest/evaluate_low_vol_veto.py;\n";
p2 += "   mypy src/; pytest tests/. Expect no delta vs main; report if anything changes.\n";
p2 += "ok=true only if all hold.\n";
let gates = agent(p2, #{ label: "gates", capability_mode: "execute", cwd: wt, output_schema: gates_schema });
if gates == () || !gates.success || gates.output == () || gates.output.ok != true {
    complete(#{ ok: false, summary: "Gates failed", gates: gates });
}
if gates.output.d_lines != 0 || gates.output.log_not_committed != true || gates.output.json_hash_match != true {
    complete(#{ ok: false, summary: "diff/log/hash gate failed", gates: gates.output });
}
if gates.output.study_claims_gone != true || gates.output.holdout_claims_remain != true {
    complete(#{ ok: false, summary: "stale-claim split incomplete", gates: gates.output });
}
log("Gates ok");

// ---------------------------------------------------------------------------
phase("OpenPR");
let p3 = "";
p3 += rules;
p3 += "Push docs/wave2a-low-vol-veto-parked and open a PR to main.\n";
p3 += "PR body: parked on develop; holdout unspent; retune prohibition; study SHA 074f843;\n";
p3 += "main base 2968d26; PYTHONPATH note; do not imply study ran at 2968d26.\n";
p3 += "DO NOT MERGE yet — prompt requires report-before-merge. Return pr_url and pr_number.\n";
let pr = agent(p3, #{ label: "open-pr", capability_mode: "all", cwd: wt, output_schema: pr_schema });
if pr == () || !pr.success || pr.output == () || pr.output.ok != true {
    complete(#{ ok: false, summary: "OpenPR failed", pr: pr });
}
log("PR opened " + pr.output.pr_url);

await_user("user", "Wave 2A parked PR is open: " + pr.output.pr_url + " — review the parked doc / claim splits, then resume to merge after CI is green (or say stop).");

// ---------------------------------------------------------------------------
phase("MergeCI");
let p4 = "";
p4 += rules;
p4 += "Wait for PR CI green on " + pr.output.pr_url + ". Paste job conclusions.\n";
p4 += "Then merge. Wait for SEPARATE main push run green. Paste both run URLs.\n";
p4 += "Reconfirm canonical holdout ledger directory still absent. ledger_still_absent=true.\n";
p4 += "ok=true only if both runs green and ledger still absent.\n";
let ci = agent(p4, #{ label: "merge-ci", capability_mode: "all", cwd: wt, output_schema: ci_schema });
if ci == () || !ci.success || ci.output == () || ci.output.ok != true {
    complete(#{ ok: false, summary: "Merge/CI failed", ci: ci, pr: pr.output });
}
if ci.output.ledger_still_absent != true {
    complete(#{ ok: false, summary: "Ledger appeared — stop", ci: ci.output });
}
log("Merged; main CI " + ci.output.main_run_url);

// ---------------------------------------------------------------------------
phase("Report");
let p5 = "";
p5 += rules;
p5 += "Write " + repo + "/scratchpad/wave2a-parked-record-report.md covering PR, stale-claim edits,\n";
p5 += "all gates, both Actions URLs, holdout still unspent, leftovers (wave2a-study 26MB CSV cleanup;\n";
p5 += "mt5-arch threads already closed or waiting on operator).\n";
p5 += "Data: prep=" + json_encode(prep.output) + " record=" + json_encode(rec.output) + "\n";
p5 += "gates=" + json_encode(gates.output) + " pr=" + json_encode(pr.output) + "\n";
p5 += "ci=" + json_encode(ci.output) + "\n";
p5 += "report_path=path. ok=true if written.\n";
let rep = agent(p5, #{ label: "report", capability_mode: "all", cwd: repo, output_schema: report_schema });
if rep == () || !rep.success || rep.output == () || rep.output.ok != true {
    complete(#{ ok: false, summary: "Report failed", report: rep });
}

let summary = "";
summary += "# wave2a-parked-record\n\n";
summary += "- PR: " + pr.output.pr_url + "\n";
summary += "- PR run: " + ci.output.pr_run_url + "\n";
summary += "- main run: " + ci.output.main_run_url + "\n";
summary += "- artifact sha256: " + prep.output.artifact_sha256 + "\n";
summary += "- report: " + rep.output.report_path + "\n";
let path = write_scratch_file("wave2a-parked-record-summary.md", summary);
complete(#{
    ok: true,
    summary: "Wave 2A parked record landed; holdout still unspent",
    path: path,
    prep: prep.output,
    record: rec.output,
    gates: gates.output,
    pr: pr.output,
    ci: ci.output,
    report: rep.output,
});
