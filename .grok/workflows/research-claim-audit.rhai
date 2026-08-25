let meta = #{
    name: "research-claim-audit",
    description: "Harden+revalidate research-doc claim auditor; FAIL on drift; prove mutant gate",
    phases: [
        #{ title: "Extract", detail: "confirm slim claim inventory" },
        #{ title: "Verify", detail: "scripts/research_claim_verify.py + negative controls" },
        #{ title: "Mutant", detail: "scripts/research_claim_mutant.py (gate_can_fail)" },
        #{ title: "Report", detail: "RESEARCH-CLAIM-AUDIT.md + commit auditor" },
    ],
};

let ext_schema = #{
    "type": "object",
    "required": ["ok", "n_claims", "n_path", "n_link", "n_sha", "n_symbol", "n_metric", "n_disposition", "inventory_path", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        n_claims: #{ "type": "integer" },
        n_path: #{ "type": "integer" },
        n_link: #{ "type": "integer" },
        n_sha: #{ "type": "integer" },
        n_symbol: #{ "type": "integer" },
        n_metric: #{ "type": "integer" },
        n_disposition: #{ "type": "integer" },
        inventory_path: #{ "type": "string" },
        evidence: #{ "type": "string" },
    },
};
let ver_schema = #{
    "type": "object",
    "required": ["ok", "n_ok", "n_drift", "n_unresolvable", "n_sha_unresolvable", "n_exempt_secrets", "n_self_referential", "n_selfref_unallowlisted", "negative_controls_ok", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        n_ok: #{ "type": "integer" },
        n_drift: #{ "type": "integer" },
        n_unresolvable: #{ "type": "integer" },
        n_sha_unresolvable: #{ "type": "integer" },
        n_exempt_secrets: #{ "type": "integer" },
        n_self_referential: #{ "type": "integer" },
        n_selfref_unallowlisted: #{ "type": "integer" },
        negative_controls_ok: #{ "type": "boolean" },
        evidence: #{ "type": "string" },
    },
};
let mut_schema = #{
    "type": "object",
    "required": ["ok", "mutant_caught", "gate_can_fail", "n_seeded", "n_caught", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        mutant_caught: #{ "type": "boolean" },
        gate_can_fail: #{ "type": "boolean" },
        n_seeded: #{ "type": "integer" },
        n_caught: #{ "type": "integer" },
        evidence: #{ "type": "string" },
    },
};
let rep_schema = #{
    "type": "object",
    "required": ["ok", "branch", "commit_sha", "report_path", "inventory_path", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        branch: #{ "type": "string" },
        commit_sha: #{ "type": "string" },
        report_path: #{ "type": "string" },
        inventory_path: #{ "type": "string" },
        evidence: #{ "type": "string" },
    },
};

let wt = if args == () { () } else { args.worktree };
if wt == () {
    pause("verification", "Pass args.worktree — path to .worktrees/.../research-claim-audit");
}

let rules = "";
rules += "HARD: never edit results/xau_charters/*, results/*_lock.json, results/xau_loop_status.md, ";
rules += "strategy_params.json, or any *.sha256. Never edit docs to make the run green. ";
rules += "No revival, no retunes, no holdout, no --live, no OrderSend, no src/mt5_arch edits. ";
rules += "Standing RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS / promote=no / live_go=false — do not change. ";
rules += "python3 for research scripts. Lint: uv run ruff check src tests AND ";
rules += "uv run ruff check scripts/research_claim_verify.py scripts/research_claim_mutant.py. ";
rules += "Phase handoff via results/*.json only — no /tmp dependency. Auditor not researcher.\n";

phase("Extract");
let p1 = "";
p1 += "Work ONLY in " + wt + "\n" + rules;
p1 += "Confirm results/research_claim_inventory.json exists (slim claims). ";
p1 += "If missing, rebuild from docs/**/*.md with kinds path/link/sha/symbol/metric/disposition. ";
p1 += "Disposition rule: treat 'BLOCKED for KEEP' (and blocked for <DISP>) as ONE token — ";
p1 += "do not emit a trailing KEEP claim from that phrase. ";
p1 += "Do not edit docs. Return counts from the inventory JSON. ";
p1 += "inventory_path=results/research_claim_inventory.json. ok=true if inventory present with n_claims>0.\n";
let ext = agent(p1, #{ label: "extract", capability_mode: "execute", cwd: wt, output_schema: ext_schema });
if ext == () || !ext.success || ext.output == () || ext.output.ok != true {
    complete(#{ ok: false, summary: "Extract failed", extract: ext });
}

phase("Verify");
let p2 = "";
p2 += "Work ONLY in " + wt + "\n" + rules;
p2 += "Run the tracked verifier (do not reimplement):\n";
p2 += "  python3 scripts/research_claim_verify.py --out results/research_claim_verify_result.json\n";
p2 += "  python3 scripts/research_claim_verify.py --negative-controls --out results/research_claim_negative_controls.json\n";
p2 += "Read both JSON results. ok=true only if verify completed AND negative_controls all_red=true ";
p2 += "AND n_sha_unresolvable==0 AND n_selfref_unallowlisted==0 (self_referential fatal unless allowlisted). ";
p2 += "If any negative control is green, ok=false and stop. ";
p2 += "Return n_ok, n_drift, n_unresolvable, n_sha_unresolvable, n_exempt_secrets, n_self_referential, n_selfref_unallowlisted; ";
p2 += "negative_controls_ok from the controls run. ";
p2 += "evidence must quote the drift[] entries, exempt_secrets (esp. config/local.paths), ";
p2 += "confirm exog v4 SHA 3dec09ef… resolves OK, and the four control names with RED/GREEN. ";
p2 += "Expected on this tree: n_drift==1 (docs/README.md:21 New edge). n_drift==0 means regression.\n";
let ver = agent(p2, #{ label: "verify", capability_mode: "execute", cwd: wt, output_schema: ver_schema });
if ver == () || !ver.success || ver.output == () || ver.output.ok != true {
    complete(#{ ok: false, summary: "Verify or negative-controls failed", verify: ver });
}
if ver.output.negative_controls_ok != true {
    complete(#{ ok: false, summary: "Anti-overcorrection gate failed — negative control went green", verify: ver.output });
}
let n_sha_bad = if ver.output.n_sha_unresolvable == () { 0 } else { ver.output.n_sha_unresolvable };
if n_sha_bad > 0 {
    complete(#{ ok: false, summary: "n_sha_unresolvable>0 — digest integrity gap is fatal", verify: ver.output });
}

phase("Mutant");
let p3 = "";
p3 += "Work ONLY in " + wt + "\n" + rules;
p3 += "Run the tracked mutant gate (do not reimplement):\n";
p3 += "  python3 scripts/research_claim_mutant.py --out results/research_claim_mutant_result.json\n";
p3 += "It must: seed >=6 known-bad claims in scratch only; route them through ";
p3 += "scripts/research_claim_verify.resolve_one (same entry as Verify); ";
p3 += "score caught ONLY when status==drift; include metric_digit, metric_md_writeup, ";
p3 += "AND metric_nested_json (results/xau_runs/*/report.json); ";
p3 += "prove gate_can_fail=true; mutant_caught=true with 6/6 all status==drift.\n";
let mut = agent(p3, #{ label: "mutant", capability_mode: "execute", cwd: wt, output_schema: mut_schema });
if mut == () || !mut.success || mut.output == () || mut.output.ok != true {
    complete(#{ ok: false, summary: "Mutant gate failed to run", mutant: mut });
}
if mut.output.mutant_caught != true || mut.output.gate_can_fail != true {
    complete(#{
        ok: false,
        summary: "Mutant gate: mutant_caught/gate_can_fail not both true",
        mutant: mut.output,
        verify: ver.output,
    });
}

phase("Report");
let p4 = "";
p4 += "Work ONLY in " + wt + "\n" + rules;
p4 += "Update docs/research/RESEARCH-CLAIM-AUDIT.md with:\n";
p4 += "- corrected drift table from results/research_claim_verify_result.json (drift[])\n";
p4 += "- per-kind counts; n_ok/n_drift/n_unresolvable/n_exempt_secrets\n";
p4 += "- checker-bug fixes B (secrets/gitignore exempt) and C (BLOCKED for KEEP) ";
p4 += "with the four negative controls (all RED) from results/research_claim_negative_controls.json\n";
p4 += "- mutant + gate_can_fail from results/research_claim_mutant_result.json\n";
p4 += "- explicit note: prior run commit 7ac2233 mutant_caught was STALE and is superseded\n";
p4 += "- THIS IS AN AUDIT, NOT AN AUTHORIZATION section\n";
p4 += "Track auditor in git: scripts/research_claim_verify.py, scripts/research_claim_mutant.py, ";
p4 += ".grok/workflows/research-claim-audit.rhai, report, inventory, verify/mutant/negcontrol JSON results.\n";
p4 += "Run: uv run ruff check src tests ; uv run ruff check scripts/research_claim_verify.py scripts/research_claim_mutant.py\n";
p4 += "Commit on research/research-claim-audit. No PR. No merge. Do not edit docs/README.md or ZACKS lane doc.\n";
p4 += "ok=true when report written AND commit succeeds (even if n_drift>0).\n";
let n_drift_s = if ver.output.n_drift == () { "unknown" } else { ver.output.n_drift.to_string() };
p4 += "Verify n_drift=" + n_drift_s + ". Expected residual drift == 1 (Zacks New edge). Document faithfully.\n";
let rep = agent(p4, #{ label: "report", capability_mode: "execute", cwd: wt, output_schema: rep_schema });
if rep == () || !rep.success || rep.output == () {
    complete(#{ ok: false, summary: "Report/commit failed", report: rep });
}
let rep_committed = rep.output.commit_sha != () && rep.output.commit_sha != "";
if rep.output.ok != true && !rep_committed {
    complete(#{ ok: false, summary: "Report/commit failed", report: rep });
}

let n_claims = if ext.output.n_claims == () { 0 } else { ext.output.n_claims };
let n_ok = if ver.output.n_ok == () { 0 } else { ver.output.n_ok };
let n_drift = if ver.output.n_drift == () { 0 } else { ver.output.n_drift };
let n_unres = if ver.output.n_unresolvable == () { 0 } else { ver.output.n_unresolvable };
let n_ex = if ver.output.n_exempt_secrets == () { 0 } else { ver.output.n_exempt_secrets };

let summary = "# research-claim-audit\n";
summary += "- n_claims: " + n_claims.to_string() + "\n";
summary += "- n_ok: " + n_ok.to_string() + "\n";
summary += "- n_drift: " + n_drift.to_string() + "\n";
summary += "- n_unresolvable: " + n_unres.to_string() + "\n";
summary += "- n_exempt_secrets: " + n_ex.to_string() + "\n";
summary += "- negative_controls_ok: true\n";
summary += "- mutant_caught: true\n";
summary += "- gate_can_fail: true\n";
summary += "- commit: " + rep.output.commit_sha + "\n";
summary += "- report: " + rep.output.report_path + "\n";
let path = write_scratch_file("research-claim-audit-summary.md", summary);

// Hardening success on this tree is n_drift==1 (Zacks New edge). Zero is a regression.
if n_drift == 0 {
    complete(#{
        ok: false,
        summary: "research-claim-audit: n_drift==0 on this tree is checker REGRESSION (expected 1 Zacks New edge)",
        n_claims: n_claims,
        n_ok: n_ok,
        n_drift: n_drift,
        n_unresolvable: n_unres,
        n_exempt_secrets: n_ex,
        mutant_caught: true,
        gate_can_fail: true,
        branch: rep.output.branch,
        commit_sha: rep.output.commit_sha,
        report_path: rep.output.report_path,
        path: path,
    });
}
if n_drift > 0 {
    complete(#{
        ok: false,
        summary: "research-claim-audit: DRIFT (expected residual n_drift==1 Zacks New edge; audit FAIL)",
        n_claims: n_claims,
        n_ok: n_ok,
        n_drift: n_drift,
        n_unresolvable: n_unres,
        n_exempt_secrets: n_ex,
        mutant_caught: true,
        gate_can_fail: true,
        negative_controls_ok: true,
        branch: rep.output.branch,
        commit_sha: rep.output.commit_sha,
        report_path: rep.output.report_path,
        inventory_path: rep.output.inventory_path,
        path: path,
    });
}

complete(#{
    ok: true,
    summary: "research-claim-audit complete — zero drift",
    n_claims: n_claims,
    n_ok: n_ok,
    n_drift: n_drift,
    n_unresolvable: n_unres,
    n_exempt_secrets: n_ex,
    mutant_caught: true,
    gate_can_fail: true,
    branch: rep.output.branch,
    commit_sha: rep.output.commit_sha,
    report_path: rep.output.report_path,
    inventory_path: rep.output.inventory_path,
    path: path,
});
