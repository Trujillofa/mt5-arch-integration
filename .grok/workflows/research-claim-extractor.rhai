let meta = #{
    name: "research-claim-extractor",
    description: "Deterministic docs claim extractor; reconcile vs frozen 435; CI-enforced rebuild",
    phases: [
        #{ title: "Design", detail: "scope decision; mirror instruction extractor; measure baseline" },
        #{ title: "Implement", detail: "scripts/research_claim_extract.py + wire verify/mutant" },
        #{ title: "Reconcile", detail: "three-way vs frozen 435; no net loss" },
        #{ title: "Allowlist", detail: "re-derive selfref allow; mutant + neg controls" },
        #{ title: "Gates", detail: "byte-identical rebuild; n_claims rises; ruff; pytest" },
        #{ title: "PRAndCI", detail: "PR + green PR/main push; tree-clean claim-audit" },
        #{ title: "Report", detail: "lists, scope, drift findings, URLs" },
    ],
};

let design_schema = #{
    "type": "object",
    "required": ["ok", "scope", "scope_rationale", "design_choice", "baseline_research_claims", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        scope: #{ "type": "string" },
        scope_rationale: #{ "type": "string" },
        design_choice: #{ "type": "string" },
        baseline_research_claims: #{ "type": "integer" },
        evidence: #{ "type": "string" },
    },
};
let impl_schema = #{
    "type": "object",
    "required": ["ok", "script_path", "entry_point", "stdlib_only", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        script_path: #{ "type": "string" },
        entry_point: #{ "type": "string" },
        stdlib_only: #{ "type": "boolean" },
        evidence: #{ "type": "string" },
    },
};
let recon_schema = #{
    "type": "object",
    "required": ["ok", "extractor_miss", "hand_walk_omit", "new_since", "n_frozen", "n_extracted_research", "net_ok", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        extractor_miss: #{ "type": "integer" },
        hand_walk_omit: #{ "type": "integer" },
        new_since: #{ "type": "integer" },
        n_frozen: #{ "type": "integer" },
        n_extracted_research: #{ "type": "integer" },
        net_ok: #{ "type": "boolean" },
        evidence: #{ "type": "string" },
    },
};
let allow_schema = #{
    "type": "object",
    "required": ["ok", "n_selfref_unallowlisted", "mutant_caught", "controls_ok", "n_drift", "drift_report", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        n_selfref_unallowlisted: #{ "type": "integer" },
        mutant_caught: #{ "type": "boolean" },
        controls_ok: #{ "type": "boolean" },
        n_drift: #{ "type": "integer" },
        drift_report: #{ "type": "string" },
        evidence: #{ "type": "string" },
    },
};
let gates_schema = #{
    "type": "object",
    "required": ["ok", "byte_identical", "n_claims", "n_results_tracked", "n_drift", "n_selfref_unallowlisted", "n_sha_unresolvable", "ruff_ok", "pytest_before", "pytest_after", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        byte_identical: #{ "type": "boolean" },
        n_claims: #{ "type": "integer" },
        n_results_tracked: #{ "type": "integer" },
        n_drift: #{ "type": "integer" },
        n_selfref_unallowlisted: #{ "type": "integer" },
        n_sha_unresolvable: #{ "type": "integer" },
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
    pause("verification", "Pass args.worktree (claim-extractor) and args.repo");
}

let rules = "";
rules += "HARD: infrastructure only — no screens/backtests/sealed_cycle/fetch_data/--live/holdout peek. ";
rules += "Do not edit results/xau_loop_status.md. Do not add numpy/pandas to pyproject.toml. ";
rules += "claim-audit stays stdlib-only. Do not force-push main. Do not delete branches. ";
rules += "A smaller research-doc claim set than the frozen 435 is a REGRESSION — stop. ";
rules += "Do not narrow scope to silence drift. Do not hand-edit research_claim_selfref_allow.json — re-derive. ";
rules += "Do not refresh inventory from CI under --fail-on-drift (tree must stay clean). ";
rules += "Work ONLY in the clean worktree; do not carry main-worktree dirty docs. Use tools.\n";

// ---------------------------------------------------------------------------
phase("Design");
let p0 = "";
p0 += rules;
p0 += "Worktree: " + wt + " (feat/research-claim-extractor @ origin/main d412721).\n";
p0 += "Read scripts/research_claim_instruction.py (model), research_claim_verify.py (flags, verify_all),\n";
p0 += "results/research_claim_inventory.json (method field + 435 research-doc claims), and the prompt\n";
p0 += "at " + repo + "/scratchpad/grok-prompt-claim-extractor.md.\n";
p0 += "Confirm: no rebuild flag today; Extract was agent prose; gap is 9/48 docs.\n";
p0 += "Decide scope: prefer ALL docs/**/*.md (includes 5 never-covered platform docs + 4 new).\n";
p0 += "State scope and scope_rationale explicitly. design_choice: prefer separate\n";
p0 += "scripts/research_claim_extract.py (keeps verifier read-only under --fail-on-drift).\n";
p0 += "baseline_research_claims must be 435. ok=true after measurements pasted in evidence.\n";
let design = agent(p0, #{ label: "design", capability_mode: "read-only", cwd: wt, output_schema: design_schema });
if design == () || !design.success || design.output == () || design.output.ok != true {
    complete(#{ ok: false, summary: "Design failed", design: design });
}
if design.output.baseline_research_claims != 435 {
    complete(#{ ok: false, summary: "baseline research-doc count != 435", design: design.output });
}
log("Design scope=" + design.output.scope);

// ---------------------------------------------------------------------------
phase("Implement");
let p1 = "";
p1 += rules;
p1 += "Implement in " + wt + ".\n";
p1 += "Create scripts/research_claim_extract.py (stdlib-only) that:\n";
p1 += "- Walks the decided scope (git ls-files docs/**/*.md or equivalent tracked-only).\n";
p1 += "- Emits slim claims {file,line,kind,claimed,attribution} for kinds:\n";
p1 += "  path, link, sha, symbol, metric, disposition — mirror frozen inventory patterns.\n";
p1 += "- Merges with extract_instruction_claims() + build_consistency_claims() from\n";
p1 += "  research_claim_instruction.py into a full inventory.\n";
p1 += "- Sorts by (file, line, kind, claimed) for byte-identical determinism.\n";
p1 += "- Replaces method field with script+entry-point name (not agent prose).\n";
p1 += "- Keeps schema research_claim_inventory/v1 unless shape changes (then bump + say why).\n";
p1 += "- CLI: write results/research_claim_inventory.json by default; support --out; never write when\n";
p1 += "  a --check/--dry-run is used if you add one.\n";
p1 += "Wire research_claim_verify.py so a normal non-fail-on-drift path can still merge instruction\n";
p1 += "claims as today; do NOT make --fail-on-drift rebuild/write inventory.\n";
p1 += "Optionally add a thin --rebuild-inventory on verify that delegates to the extract module,\n";
p1 += "but keep extract as the primary entry.\n";
p1 += "Update docs/research/RESEARCH-CLAIM-AUDIT.md to describe the extractor as code.\n";
p1 += "Update .github/workflows/ci.yml claim-audit ONLY if needed for ruff list — do not add deps.\n";
p1 += "Also ruff-check the new script in the lint job's auditor script list.\n";
p1 += "stdlib_only=true required. Commit WIP as needed. ok=true when script runs on this tree.\n";
let impl = agent(p1, #{ label: "implement", capability_mode: "all", cwd: wt, output_schema: impl_schema });
if impl == () || !impl.success || impl.output == () || impl.output.ok != true {
    complete(#{ ok: false, summary: "Implement failed", implement: impl });
}
if impl.output.stdlib_only != true {
    complete(#{ ok: false, summary: "Extractor not stdlib-only", implement: impl.output });
}
log("Implement " + impl.output.script_path);

// ---------------------------------------------------------------------------
phase("Reconcile");
let p2 = "";
p2 += rules;
p2 += "THREE-WAY RECONCILIATION (load-bearing).\n";
p2 += "Save frozen research-doc claims (docs/** excluding consistency) from the committed inventory\n";
p2 += "BEFORE overwrite (copy to /tmp/frozen_research_claims.json).\n";
p2 += "Run extractor; compare extracted research-doc claims to frozen 435 keyed by\n";
p2 += "(file, line, kind, claimed) [attribution may differ — note it].\n";
p2 += "Classify EVERY difference:\n";
p2 += "1) extractor_miss — frozen has it, extractor does not → BUG; FIX before continuing.\n";
p2 += "2) hand_walk_omit — extractor finds real claim frozen missed → list (gain).\n";
p2 += "3) new_since — from docs absent at 52c6baf / the 9 uncovered files → list by file.\n";
p2 += "n_frozen=435. n_extracted_research = count of research-doc claims from extractor.\n";
p2 += "net_ok=true only if extractor_miss==0 AND n_extracted_research >= 435.\n";
p2 += "A smaller set is a regression — set ok=false and stop with full miss list.\n";
p2 += "Paste counts + lists (or paths to list files under scratchpad/) in evidence.\n";
let recon = agent(p2, #{ label: "reconcile", capability_mode: "all", cwd: wt, output_schema: recon_schema });
if recon == () || !recon.success || recon.output == () || recon.output.ok != true {
    complete(#{ ok: false, summary: "Reconcile failed", reconcile: recon });
}
if recon.output.extractor_miss != 0 || recon.output.net_ok != true {
    complete(#{ ok: false, summary: "Extractor miss / net loss — stop", reconcile: recon.output });
}
log("Reconcile ok extracted=" + recon.output.n_extracted_research.to_string());

// ---------------------------------------------------------------------------
phase("Allowlist");
let p3 = "";
p3 += rules;
p3 += "Scope changed by construction — RE-DERIVE results/research_claim_selfref_allow.json.\n";
p3 += "Do not hand-edit. Search tracked results/** (same spirit as existing allow file note):\n";
p3 += "for each self_referential claim after verify, record n_searched + searched_sample + reason.\n";
p3 += "You may add scripts/research_claim_selfref_rebuild.py or a function in extract/verify.\n";
p3 += "Then: python3 scripts/research_claim_verify.py --fail-on-drift --out /tmp/claim-extract.json\n";
p3 += "Require n_selfref_unallowlisted==0. Report n_drift — if newly-covered docs surface real drift,\n";
p3 += "that is a FINDING: list file/line/claimed/actual in drift_report. Fix the doc OR exclude with\n";
p3 += "explicit documented reason — do NOT narrow whole scope to stay green.\n";
p3 += "If n_drift>0 after honest handling, ok can still be true only if each item is fixed or\n";
p3 += "explicitly documented excluded; otherwise ok=false.\n";
p3 += "Run python3 scripts/research_claim_mutant.py — mutant_caught=true (all seeds).\n";
p3 += "If mutant harness must learn about the new extractor, say so and wire it — do not leave it\n";
p3 += "testing only the old frozen path.\n";
p3 += "Run negative controls — controls_ok=true.\n";
p3 += "Commit inventory + allowlist + extractor + audit doc updates.\n";
let allow = agent(p3, #{ label: "allowlist-mutant", capability_mode: "all", cwd: wt, output_schema: allow_schema });
if allow == () || !allow.success || allow.output == () || allow.output.ok != true {
    complete(#{ ok: false, summary: "Allowlist/mutant/drift handling failed", allow: allow });
}
if allow.output.n_selfref_unallowlisted != 0 || allow.output.mutant_caught != true || allow.output.controls_ok != true {
    complete(#{ ok: false, summary: "Gate soft-fail on allow/mutant/controls", allow: allow.output });
}
log("Allowlist ok n_drift=" + allow.output.n_drift.to_string());

// ---------------------------------------------------------------------------
phase("Gates");
let p4 = "";
p4 += rules;
p4 += "GATES — paste real output:\n";
p4 += "1) Run extract TWICE; second run leaves porcelain empty OR two outputs sha256-equal.\n";
p4 += "   byte_identical=true required.\n";
p4 += "2) verify --fail-on-drift: n_claims MUST be > 531 (flat 531 = extractor did not take over).\n";
p4 += "   Also n_drift, n_selfref_unallowlisted, n_sha_unresolvable, n_results_tracked.\n";
p4 += "3) ruff: uv run ruff check src tests AND all scripts/research_claim_*.py\n";
p4 += "4) pytest before/after: uv run pytest -q -m 'not live' (~812). Report strings.\n";
p4 += "ok=true only if byte_identical and n_claims>531 and n_drift==0 and n_selfref_unallowlisted==0\n";
p4 += "and n_sha_unresolvable==0 and ruff_ok.\n";
let gates = agent(p4, #{ label: "gates", capability_mode: "execute", cwd: wt, output_schema: gates_schema });
if gates == () || !gates.success || gates.output == () || gates.output.ok != true {
    complete(#{ ok: false, summary: "Gates failed", gates: gates });
}
if gates.output.n_claims <= 531 {
    complete(#{ ok: false, summary: "n_claims did not rise above 531 — extractor did not take over", gates: gates.output });
}
if gates.output.byte_identical != true || gates.output.n_drift != 0 {
    complete(#{ ok: false, summary: "byte-identical or n_drift gate failed", gates: gates.output });
}
log("Gates ok n_claims=" + gates.output.n_claims.to_string());

// ---------------------------------------------------------------------------
phase("PRAndCI");
let p5 = "";
p5 += rules;
p5 += "Push feat/research-claim-extractor; open PR. Body must cover: design (script vs flag),\n";
p5 += "scope decision, three-way reconciliation summary, any drift findings, that n_claims rose,\n";
p5 += "selfref re-derived, mutant still catches.\n";
p5 += "Wait for PR CI all green; confirm claim-audit tree-clean. Merge.\n";
p5 += "Wait for SEPARATE main push run all green. Paste both URLs.\n";
p5 += "tree_clean=true from claim-audit job. ok=true only if pr_tests and main_tests and\n";
p5 += "pr_claim_audit and main_claim_audit are success.\n";
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
p6 += "Write " + repo + "/scratchpad/research-claim-extractor-report.md with full three-way lists,\n";
p6 += "scope decision, drift findings, all gate numbers, both Actions URLs, left undone.\n";
p6 += "Data: design=" + json_encode(design.output) + " impl=" + json_encode(impl.output) + "\n";
p6 += "recon=" + json_encode(recon.output) + " allow=" + json_encode(allow.output) + "\n";
p6 += "gates=" + json_encode(gates.output) + " ci=" + json_encode(ci.output) + "\n";
p6 += "report_path=path. ok=true if written.\n";
let rep = agent(p6, #{ label: "report", capability_mode: "all", cwd: repo, output_schema: report_schema });
if rep == () || !rep.success || rep.output == () || rep.output.ok != true {
    complete(#{ ok: false, summary: "Report failed", report: rep });
}

let summary = "";
summary += "# research-claim-extractor\n\n";
summary += "- PR: " + ci.output.pr_url + "\n";
summary += "- n_claims: " + gates.output.n_claims.to_string() + " (was 531)\n";
summary += "- extractor_miss: " + recon.output.extractor_miss.to_string() + "\n";
summary += "- PR run: " + ci.output.pr_run_url + "\n";
summary += "- main run: " + ci.output.main_run_url + "\n";
summary += "- report: " + rep.output.report_path + "\n";
let path = write_scratch_file("research-claim-extractor-summary.md", summary);
complete(#{
    ok: true,
    summary: "deterministic claim extractor landed; n_claims rose",
    path: path,
    design: design.output,
    implement: impl.output,
    reconcile: recon.output,
    allow: allow.output,
    gates: gates.output,
    ci: ci.output,
    report: rep.output,
});
