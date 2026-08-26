let meta = #{
    name: "simulator-conformance",
    description: "Hand-derived simulator contract conformance (no research / no revival)",
    phases: [
        #{ title: "Inventory", detail: "engines + clauses C1-C10" },
        #{ title: "Fixtures", detail: "hand-derived golden fixtures" },
        #{ title: "Conform", detail: "pytest + mutant + regression gates" },
        #{ title: "Report", detail: "SIMULATOR-CONFORMANCE.md + commit" },
    ],
};

let inv_schema = #{
    "type": "object",
    "required": ["ok", "n_engines", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        n_engines: #{ "type": "integer" },
        evidence: #{ "type": "string" },
    },
};
let fix_schema = #{
    "type": "object",
    "required": ["ok", "n_fixtures", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        n_fixtures: #{ "type": "integer" },
        evidence: #{ "type": "string" },
    },
};
let conf_schema = #{
    "type": "object",
    "required": ["ok", "n_pass", "n_divergence", "mutant_caught", "regression_green", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        n_pass: #{ "type": "integer" },
        n_divergence: #{ "type": "integer" },
        mutant_caught: #{ "type": "boolean" },
        regression_green: #{ "type": "boolean" },
        evidence: #{ "type": "string" },
    },
};
let rep_schema = #{
    "type": "object",
    "required": ["ok", "branch", "commit_sha", "report_path", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        branch: #{ "type": "string" },
        commit_sha: #{ "type": "string" },
        report_path: #{ "type": "string" },
        evidence: #{ "type": "string" },
    },
};

let wt = if args == () { () } else { args.worktree };
if wt == () {
    pause("verification", "Pass args.worktree — path to .worktrees/.../simulator-conformance");
}

let rules = "";
rules += "HARD: hand-derived expected values only; no engine edits to force PASS; no lock/charter/status edits; ";
rules += "no revival; python3 not uv run for tests; uv run ruff check for lint.\n";

phase("Inventory");
let p1 = "";
p1 += "Work ONLY in " + wt + "\n" + rules;
p1 += "Read inventory at tests/fixtures/simulator_conformance/inventory.json if present; else enumerate engines from prompt.\n";
p1 += "Return ok=true and n_engines. evidence=brief.\n";
let inv = agent(p1, #{ label: "inventory", capability_mode: "read-only", cwd: wt, output_schema: inv_schema });
if inv == () || !inv.success || inv.output == () || inv.output.ok != true {
    complete(#{ ok: false, summary: "Inventory failed", inventory: inv });
}

phase("Fixtures");
let p2 = "";
p2 += "Work ONLY in " + wt + "\n" + rules;
p2 += "Ensure hand-derived fixtures exist under tests/fixtures/simulator_conformance/ with derivation strings.\n";
p2 += "Do not capture expected values from engine runs. ok=true if fixtures present with derivations.\n";
let fix = agent(p2, #{ label: "fixtures", capability_mode: "execute", cwd: wt, output_schema: fix_schema });
if fix == () || !fix.success || fix.output == () || fix.output.ok != true {
    complete(#{ ok: false, summary: "Fixtures failed", fixtures: fix });
}

phase("Conform");
let p3 = "";
p3 += "Work ONLY in " + wt + "\n" + rules;
p3 += "Run: python3 -m pytest tests/test_simulator_conformance.py -q\n";
p3 += "Confirm mutant_caught (SL-first mutant test). Run regression: ";
p3 += "python3 -m pytest tests/test_eurusd_ny_scalp.py tests/test_xau_pipeline.py tests/test_htf_fib_pivot_confirmation.py -q\n";
p3 += "Do not edit engines. n_divergence=0 expected. ok=false if mutant not caught or regression red.\n";
let conf = agent(p3, #{ label: "conform", capability_mode: "execute", cwd: wt, output_schema: conf_schema });
if conf == () || !conf.success || conf.output == () || conf.output.ok != true {
    complete(#{ ok: false, summary: "Conform failed", conform: conf });
}
if conf.output.mutant_caught != true || conf.output.regression_green != true {
    complete(#{ ok: false, summary: "Gates failed", conform: conf.output });
}

phase("Report");
let p4 = "";
p4 += "Work ONLY in " + wt + "\n" + rules;
p4 += "Ensure docs/research/SIMULATOR-CONFORMANCE.md exists with matrix + no-revival section.\n";
p4 += "Commit on research/simulator-conformance. No PR. No merge. Return commit_sha and report_path.\n";
let rep = agent(p4, #{ label: "report", capability_mode: "execute", cwd: wt, output_schema: rep_schema });
if rep == () || !rep.success || rep.output == () || rep.output.ok != true {
    complete(#{ ok: false, summary: "Report/commit failed", report: rep });
}

let summary = "# simulator-conformance\n";
summary += "- n_engines: " + inv.output.n_engines.to_string() + "\n";
summary += "- n_pass: " + conf.output.n_pass.to_string() + "\n";
summary += "- n_divergence: " + conf.output.n_divergence.to_string() + "\n";
summary += "- mutant_caught: true\n";
summary += "- regression_green: true\n";
summary += "- commit: " + rep.output.commit_sha + "\n";
let path = write_scratch_file("simulator-conformance-summary.md", summary);
complete(#{
    ok: true,
    summary: "simulator-conformance complete",
    n_engines: inv.output.n_engines,
    n_clauses_tested: conf.output.n_pass,
    n_pass: conf.output.n_pass,
    n_divergence: conf.output.n_divergence,
    mutant_caught: true,
    regression_green: true,
    branch: rep.output.branch,
    commit_sha: rep.output.commit_sha,
    report_path: rep.output.report_path,
    path: path,
});
