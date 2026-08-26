let meta = #{
    name: "xau-asia-box-v2-reverify",
    description: "Adversarial re-verify asia_box_london_sweep_fade_flat v2 freeze vs F1 matrix",
    phases: [
        #{ title: "Pins", detail: "SHA, validate, costs/null/gates/K identity" },
        #{ title: "Structural", detail: "diff vs v1: only expected CHANGED/ADDED" },
        #{ title: "Gap policy", detail: "entry_gap_policy covers a/b/c + fixtures" },
    ],
};

let pin_schema = #{
    "type": "object",
    "required": ["ok", "v2_sha", "validate_v1", "validate_v2", "costs_identical", "null_identical", "gates_identical", "multiplicity_identical", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        v2_sha: #{ "type": "string" },
        validate_v1: #{ "type": "array", "items": #{ "type": "string" } },
        validate_v2: #{ "type": "array", "items": #{ "type": "string" } },
        costs_identical: #{ "type": "boolean" },
        null_identical: #{ "type": "boolean" },
        gates_identical: #{ "type": "boolean" },
        multiplicity_identical: #{ "type": "boolean" },
        evidence: #{ "type": "string" },
    },
};

let struct_schema = #{
    "type": "object",
    "required": ["ok", "changed", "unexpected_changes", "added_gap_policy", "supersedes_v1_sha_ok", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        changed: #{ "type": "array", "items": #{ "type": "string" } },
        unexpected_changes: #{ "type": "array", "items": #{ "type": "string" } },
        added_gap_policy: #{ "type": "boolean" },
        supersedes_v1_sha_ok: #{ "type": "boolean" },
        evidence: #{ "type": "string" },
    },
};

let gap_schema = #{
    "type": "object",
    "required": ["ok", "skip_beyond_sl", "skip_beyond_tp", "skip_degenerate", "fixtures_present", "no_develop_metrics", "evidence"],
    "properties": #{
        ok: #{ "type": "boolean" },
        skip_beyond_sl: #{ "type": "boolean" },
        skip_beyond_tp: #{ "type": "boolean" },
        skip_degenerate: #{ "type": "boolean" },
        fixtures_present: #{ "type": "boolean" },
        no_develop_metrics: #{ "type": "boolean" },
        evidence: #{ "type": "string" },
    },
};

let wt = if args == () { () } else { args.worktree };
if wt == () {
    pause("verification", "Pass args.worktree — path to mt5-arch-integration-wt-liq-sweep-fade");
}

phase("Pins");
let pin_prompt = "";
pin_prompt += "Work ONLY in worktree: " + wt + "\n";
pin_prompt += "Read-only except running validation commands. Return JSON schema fields.\n";
pin_prompt += "1) Confirm v2 sidecar SHA matches file bytes for results/xau_charters/2026-08-19_asia_box_london_sweep_fade_flat_v2.json\n";
pin_prompt += "2) validate_charter_file on v1 and v2 — both must be []\n";
pin_prompt += "3) Assert fixed.costs, null, gates, multiplicity are deep-equal between v1 and v2\n";
pin_prompt += "4) Set ok=true only if all pass. evidence = short command outputs.\n";
let pin = agent(pin_prompt, #{
    label: "pins",
    capability_mode: "execute",
    cwd: wt,
    output_schema: pin_schema,
});
if pin == () || !pin.success || pin.output == () || pin.output.ok != true {
    complete(#{
        ok: false,
        summary: "PIN checks failed or unverified",
        pin: pin,
    });
}

phase("Structural");
let st_prompt = "";
st_prompt += "Work ONLY in worktree: " + wt + "\n";
st_prompt += "Adversarially diff v1 vs v2 JSON. Allowed CHANGED: charter_version, display_name, thesis_memo, execution_contract.required_fixtures, explicitly_forbidden; ADDED supersedes.* and rule.entry_gap_policy.*.\n";
st_prompt += "Flag any other CHANGED path as unexpected_changes. Confirm supersedes.sha256 == v1 file SHA 7cf9f46fd5ddd44c171f04260f8d4fac167cb005bf3f6d4d03c1c137c1399b7e.\n";
st_prompt += "ok=true only if unexpected_changes empty and gap policy + supersedes present.\n";
let st = agent(st_prompt, #{
    label: "structural",
    capability_mode: "execute",
    cwd: wt,
    output_schema: struct_schema,
});
if st == () || !st.success || st.output == () || st.output.ok != true {
    complete(#{
        ok: false,
        summary: "Structural diff failed or unexpected changes",
        pin: pin.output,
        structural: st,
    });
}

phase("Gap policy");
let gap_prompt = "";
gap_prompt += "Work ONLY in worktree: " + wt + "\n";
gap_prompt += "Read v2 charter rule.entry_gap_policy and v2 memo. Confirm skip_entry for (a) open beyond own SL, (b) open beyond TP, (c) degenerate box. Confirm fixtures entry_gap_open_beyond_sl_skipped, entry_gap_open_beyond_tp_skipped, entry_gap_degenerate_box_skipped are listed. Confirm v2 memo has no develop PF/NP/DD of this rule. ok=true only if all hold; cite evidence.\n";
let gap = agent(gap_prompt, #{
    label: "gap-policy",
    capability_mode: "read-only",
    cwd: wt,
    output_schema: gap_schema,
});
if gap == () || !gap.success || gap.output == () || gap.output.ok != true {
    complete(#{
        ok: false,
        summary: "Gap policy / memo check failed",
        pin: pin.output,
        structural: st.output,
        gap: gap,
    });
}

let report = "# asia_box v2 re-verify\n\n";
report += "- pins_ok: true\n";
report += "- structural_ok: true\n";
report += "- gap_policy_ok: true\n";
report += "- v2_sha: " + pin.output.v2_sha + "\n";
report += "- next: AWAIT_AUTHORIZE then implementation+fixtures only; no screen\n";
let path = write_scratch_file("asia-box-v2-reverify.md", report);
complete(#{
    ok: true,
    summary: "v2 freeze re-verify PASS — await AUTHORIZE for implementation",
    v2_sha: pin.output.v2_sha,
    pin: pin.output,
    structural: st.output,
    gap: gap.output,
    path: path,
});
