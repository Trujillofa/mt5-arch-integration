let meta = #{
    name: "claim-extractor-precision",
    description: "Precision pass: shrink non-constraining claims; preserve n_ok; attribute metrics",
    phases: [
        #{ title: "Baseline", detail: "freeze ok-bucket keys; confirm inverted success criteria" },
        #{ title: "FixDefects", detail: "attribute metrics; skip findings-table/thresholds; longest metric span" },
        #{ title: "OkPreserve", detail: "Gate 3: removed-from-ok set empty; n_ok floor; frozen 435 intact" },
        #{ title: "AllowRebuild", detail: "re-derive selfref allow; mutant + controls" },
        #{ title: "Gates", detail: "n_claims down; constraining>85.3%; byte-identical; ruff; pytest" },
        #{ title: "PRAndCI", detail: "PR + green PR/main push; tree-clean" },
        #{ title: "Report", detail: "before/after buckets; ok-diff proof; URLs" },
    ],
};

let base_schema = #{
    "type": "object",
    "required": ["ok", "n_claims", "n_ok", "n_self_referential", "n_unresolvable", "constraining", "ok_keys_path", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        n_claims: #{ "type": "integer" },
        n_ok: #{ "type": "integer" },
        n_self_referential: #{ "type": "integer" },
        n_unresolvable: #{ "type": "integer" },
        constraining: #{ "type": "number" },
        ok_keys_path: #{ "type": "string" },
        evidence: #{ "type": "string" },
    },
};
let fix_schema = #{
    "type": "object",
    "required": ["ok", "defect1", "defect2", "defect3", "stopped_emitting", "commit_sha", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        defect1: #{ "type": "string" },
        defect2: #{ "type": "string" },
        defect3: #{ "type": "string" },
        stopped_emitting: #{ "type": "string" },
        commit_sha: #{ "type": "string" },
        evidence: #{ "type": "string" },
    },
};
let preserve_schema = #{
    "type": "object",
    "required": ["ok", "n_ok", "ok_removed_count", "frozen_miss", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        n_ok: #{ "type": "integer" },
        ok_removed_count: #{ "type": "integer" },
        frozen_miss: #{ "type": "integer" },
        evidence: #{ "type": "string" },
    },
};
let allow_schema = #{
    "type": "object",
    "required": ["ok", "n_selfref_unallowlisted", "mutant_caught", "controls_ok", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        n_selfref_unallowlisted: #{ "type": "integer" },
        mutant_caught: #{ "type": "boolean" },
        controls_ok: #{ "type": "boolean" },
        evidence: #{ "type": "string" },
    },
};
let gates_schema = #{
    "type": "object",
    "required": ["ok", "n_claims", "n_ok", "n_self_referential", "n_unresolvable", "n_skipped_dates", "n_exempt_secrets", "constraining", "byte_identical", "ruff_ok", "pytest_before", "pytest_after", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        n_claims: #{ "type": "integer" },
        n_ok: #{ "type": "integer" },
        n_self_referential: #{ "type": "integer" },
        n_unresolvable: #{ "type": "integer" },
        n_skipped_dates: #{ "type": "integer" },
        n_exempt_secrets: #{ "type": "integer" },
        constraining: #{ "type": "number" },
        byte_identical: #{ "type": "boolean" },
        ruff_ok: #{ "type": "boolean" },
        pytest_before: #{ "type": "string" },
        pytest_after: #{ "type": "string" },
        evidence: #{ "type": "string" },
    },
};
let ci_schema = #{
    "type": "object",
    "required": ["ok", "pr_url", "pr_run_url", "main_run_url", "pr_lint", "pr_claim_audit", "pr_tests", "main_lint", "main_claim_audit", "main_tests", "tree_clean", "evidence"],
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
        tree_clean: #{ "type": "boolean" },
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
    pause("verification", "Pass args.worktree (claim-extractor-precision) and args.repo");
}

let rules = "";
rules += "HARD INVERSION: success makes n_claims FALL below 1413. Do NOT chase a rising headline count. ";
rules += "n_ok >= 1226 is the hard floor. No claim currently in n_ok may disappear. ";
rules += "Attribute-don't-delete for the 108 self-ref metrics; deletion only per-file with stated reason. ";
rules += "Do not churn the 302 cosmetic attribution renames. ";
rules += "No screens/backtests/--live/holdout peek. Do not edit results/xau_loop_status.md. ";
rules += "Re-derive selfref allowlist — never hand-edit. Stdlib-only claim-audit. ";
rules += "Work in clean worktree only. If a gate fails: report and STOP. Use tools.\n";

// ---------------------------------------------------------------------------
phase("Baseline");
let p0 = "";
p0 += rules;
p0 += "In " + wt + " @ origin/main (73879ab / current tip):\n";
p0 += "1) Run python3 scripts/research_claim_verify.py --out /tmp/precision-before.json\n";
p0 += "   Confirm ~n_claims=1413 n_ok=1226 n_self_referential=108 n_unresolvable=8.\n";
p0 += "2) Dump the ok-bucket keys as sorted (file, kind, claimed) JSON to scratchpad/ok_keys_before.json\n";
p0 += "   (derive from verify report's ok list / claims that resolved ok — whatever structure the\n";
p0 += "   verifier exposes; if only drift/selfref/unresolvable are listed, reconstruct ok as\n";
p0 += "   inventory claims minus non-ok buckets). ok_keys_path=that path.\n";
p0 += "3) Also snapshot frozen-435 research-doc keys for Gate 4 later.\n";
p0 += "4) State aloud in evidence: SUCCESS = n_claims DOWN, n_ok floor held, ok-removed empty.\n";
p0 += "constraining = n_ok/n_claims. ok=true with baseline numbers.\n";
let base = agent(p0, #{ label: "baseline", capability_mode: "execute", cwd: wt, output_schema: base_schema });
if base == () || !base.success || base.output == () || base.output.ok != true {
    complete(#{ ok: false, summary: "Baseline failed", baseline: base });
}
if base.output.n_ok < 1226 {
    complete(#{ ok: false, summary: "Unexpected baseline n_ok", baseline: base.output });
}
log("Baseline n_claims=" + base.output.n_claims.to_string() + " n_ok=" + base.output.n_ok.to_string());

// ---------------------------------------------------------------------------
phase("FixDefects");
let p1 = "";
p1 += rules;
p1 += "Edit scripts/research_claim_extract.py (and helpers if needed) in " + wt + ".\n";
p1 += "DEFECT 1 — attribute the 108 null-attribution metrics from enclosing table row / section\n";
p1 += "heading (hand-walk proof: SIGNAL-EDGE-TRIAGE.md:48 'n=7819' attribution='mean_reversion').\n";
p1 += "Do not hunt for lost frozen attributions — verified zero frozen claims lost attrs.\n";
p1 += "Prefer resolving against results/** oracles. Only stop emitting when no external oracle\n";
p1 += "exists; list those per file in stopped_emitting.\n";
p1 += "DEFECT 2 — skip findings-table status cells (BLOCKED/KEEP/New edge in RESEARCH-CLAIM-AUDIT\n";
p1 += "findings tables; README KEEP scrape) and threshold declarations (n < 20, n < 40). Target\n";
p1 += "n_unresolvable=0. If one of the eight is genuinely resolvable, resolve and say so.\n";
p1 += "DEFECT 3 — longest non-overlapping metric span per line; keep labelled form (t −3.13),\n";
p1 += "drop bare substring duplicates.\n";
p1 += "Do NOT open a broad attribution-renaming pass for the 302 cosmetic changes.\n";
p1 += "Rebuild inventory via extract. Commit. defect1/2/3 = short summaries. ok=true when extract runs.\n";
let fix = agent(p1, #{ label: "fix-defects", capability_mode: "all", cwd: wt, output_schema: fix_schema });
if fix == () || !fix.success || fix.output == () || fix.output.ok != true {
    complete(#{ ok: false, summary: "FixDefects failed", fix: fix });
}
log("Fixes committed " + fix.output.commit_sha);

// ---------------------------------------------------------------------------
phase("OkPreserve");
let p2 = "";
p2 += rules;
p2 += "LOAD-BEARING GATE 3.\n";
p2 += "1) Re-run verify --out /tmp/precision-after-ok.json\n";
p2 += "2) Build ok keys after as (file, kind, claimed); diff vs " + base.output.ok_keys_path + "\n";
p2 += "3) ok_removed_count MUST be 0. If non-zero, list every removed key and STOP (ok=false) —\n";
p2 += "   you deleted checked evidence.\n";
p2 += "4) n_ok MUST be >= 1226. If lower, identify which claim and STOP.\n";
p2 += "5) Re-check frozen 435 research-doc content keys still present (extractor_miss=0).\n";
p2 += "frozen_miss must be 0. Paste proof in evidence (counts + empty removed list).\n";
let preserve = agent(p2, #{ label: "ok-preserve", capability_mode: "execute", cwd: wt, output_schema: preserve_schema });
if preserve == () || !preserve.success || preserve.output == () || preserve.output.ok != true {
    complete(#{ ok: false, summary: "OkPreserve failed — stopped", preserve: preserve });
}
if preserve.output.ok_removed_count != 0 || preserve.output.n_ok < 1226 || preserve.output.frozen_miss != 0 {
    complete(#{ ok: false, summary: "Removed ok claims or n_ok/frozen regression", preserve: preserve.output });
}
log("OkPreserve n_ok=" + preserve.output.n_ok.to_string());

// ---------------------------------------------------------------------------
phase("AllowRebuild");
let p3 = "";
p3 += rules;
p3 += "Re-derive results/research_claim_selfref_allow.json (scope/attribution changed).\n";
p3 += "Never hand-edit. Confirm n_selfref_unallowlisted=0 under --fail-on-drift.\n";
p3 += "Mutant: all caught. Neg controls: all detecting. If corpus shrink weakens mutant teeth,\n";
p3 += "say so and fix harness rather than silently softening. Commit allowlist + any harness tweaks.\n";
let allow = agent(p3, #{ label: "allow-rebuild", capability_mode: "all", cwd: wt, output_schema: allow_schema });
if allow == () || !allow.success || allow.output == () || allow.output.ok != true {
    complete(#{ ok: false, summary: "AllowRebuild failed", allow: allow });
}
if allow.output.n_selfref_unallowlisted != 0 || allow.output.mutant_caught != true || allow.output.controls_ok != true {
    complete(#{ ok: false, summary: "selfref/mutant/controls gate failed", allow: allow.output });
}
log("AllowRebuild ok");

// ---------------------------------------------------------------------------
phase("Gates");
let p4 = "";
p4 += rules;
p4 += "Final verify --fail-on-drift. Report full bucket table.\n";
p4 += "REQUIRED: n_claims < 1413; n_ok >= 1226; n_self_referential < 108; n_unresolvable == 0;\n";
p4 += "constraining = n_ok/n_claims > 0.853.\n";
p4 += "Double-extract byte-identical; second run porcelain empty (ignore scratchpad).\n";
p4 += "ruff src tests + scripts/research_claim_*.py; pytest -q -m 'not live' before/after ~812.\n";
p4 += "ok=true only if all numeric requirements hold.\n";
let gates = agent(p4, #{ label: "gates", capability_mode: "execute", cwd: wt, output_schema: gates_schema });
if gates == () || !gates.success || gates.output == () || gates.output.ok != true {
    complete(#{ ok: false, summary: "Gates failed", gates: gates });
}
if gates.output.n_claims >= 1413 {
    complete(#{ ok: false, summary: "n_claims did not fall — inversion failed", gates: gates.output });
}
if gates.output.n_ok < 1226 || gates.output.n_unresolvable != 0 || gates.output.n_self_referential >= 108 {
    complete(#{ ok: false, summary: "bucket targets missed", gates: gates.output });
}
if gates.output.constraining <= 0.853 {
    complete(#{ ok: false, summary: "constraining fraction not above 85.3%", gates: gates.output });
}
log("Gates ok n_claims=" + gates.output.n_claims.to_string() + " constraining=" + gates.output.constraining.to_string());

// ---------------------------------------------------------------------------
phase("PRAndCI");
let p5 = "";
p5 += rules;
p5 += "Push feat/claim-extractor-precision; open PR. Body must stress INVERTED criterion:\n";
p5 += "n_claims fell; n_ok held; ok-removed empty; attribute-not-delete; no cosmetic churn.\n";
p5 += "Include before/after bucket table. Wait for PR CI green (tree-clean). Merge.\n";
p5 += "Wait for SEPARATE main push run green. Paste both URLs.\n";
p5 += "ok=true only if claim-audit+tests success on both runs.\n";
let ci = agent(p5, #{ label: "pr-ci", capability_mode: "all", cwd: wt, output_schema: ci_schema });
if ci == () || !ci.success || ci.output == () || ci.output.ok != true {
    complete(#{ ok: false, summary: "PR/CI failed", ci: ci, gates: gates.output });
}
if ci.output.pr_claim_audit != "success" || ci.output.main_claim_audit != "success" {
    complete(#{ ok: false, summary: "claim-audit not green", ci: ci.output });
}
log("CI green " + ci.output.pr_url);

// ---------------------------------------------------------------------------
phase("Report");
let p6 = "";
p6 += rules;
p6 += "Write " + repo + "/scratchpad/claim-extractor-precision-report.md with per-defect changes,\n";
p6 += "before/after buckets, ok-removed empty proof, stopped_emitting list, both Actions URLs,\n";
p6 += "left undone. Note multiplicity ledger + dirty main-worktree docs still operator-owned.\n";
p6 += "Data: base=" + json_encode(base.output) + " fix=" + json_encode(fix.output) + "\n";
p6 += "preserve=" + json_encode(preserve.output) + " allow=" + json_encode(allow.output) + "\n";
p6 += "gates=" + json_encode(gates.output) + " ci=" + json_encode(ci.output) + "\n";
p6 += "report_path=path. ok=true if written.\n";
let rep = agent(p6, #{ label: "report", capability_mode: "all", cwd: repo, output_schema: report_schema });
if rep == () || !rep.success || rep.output == () || rep.output.ok != true {
    complete(#{ ok: false, summary: "Report failed", report: rep });
}

let summary = "";
summary += "# claim-extractor-precision\n\n";
summary += "- PR: " + ci.output.pr_url + "\n";
summary += "- n_claims: " + base.output.n_claims.to_string() + " -> " + gates.output.n_claims.to_string() + "\n";
summary += "- n_ok: " + base.output.n_ok.to_string() + " -> " + gates.output.n_ok.to_string() + "\n";
summary += "- ok_removed: " + preserve.output.ok_removed_count.to_string() + "\n";
summary += "- constraining: " + gates.output.constraining.to_string() + "\n";
summary += "- report: " + rep.output.report_path + "\n";
let path = write_scratch_file("claim-extractor-precision-summary.md", summary);
complete(#{
    ok: true,
    summary: "precision pass: n_claims down, n_ok preserved, ok-removed empty",
    path: path,
    baseline: base.output,
    fix: fix.output,
    preserve: preserve.output,
    allow: allow.output,
    gates: gates.output,
    ci: ci.output,
    report: rep.output,
});
