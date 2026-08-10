let meta = #{
    name: "xau-charter-pr-bridge",
    description: "Adopt charter B, open draft PR to main, deploy Mt5ArchBridge v1.22 to Exness",
    phases: [
        #{ title: "Adopt-charter-B", detail: "Mark dual-layer charter adopted; link from AGENTS.md" },
        #{ title: "Draft-PR", detail: "Open GitHub draft PR from research branch to main" },
        #{ title: "Deploy-bridge", detail: "Install+compile Mt5ArchBridge v1.22 into Exness Wine prefix" },
        #{ title: "Verify", detail: "Check deployed source, optional symbols.json, tests" },
        #{ title: "Commit-push", detail: "Commit charter adoption + notes; ordinary push" },
    ],
    when_to_use: "After housekeeping; owner wants recommended next steps (B + draft PR + Exness deploy)",
};

let result_schema = #{
    "type": "object",
    "required": ["ok", "summary", "details"],
    "properties": #{
        "ok": #{ "type": "boolean" },
        "summary": #{ "type": "string" },
        "details": #{ "type": "string" },
    },
};

let root = "/home/yderf/Projects/trading/mt5-arch-integration";

// ---------------------------------------------------------------------------
phase("Adopt-charter-B");
log("Formally adopt dual-layer charter Option B");

let ch_prompt = "";
ch_prompt += "Repo: " + root + "\n";
ch_prompt += "SAFETY: offline docs. No --live. No force-push. No merge of PR.\n\n";
ch_prompt += "Owner decision: **adopt Option B** (explicit dual-layer charter).\n\n";
ch_prompt += "1. Edit docs/CHARTER-RESEARCH-LAYER.md:\n";
ch_prompt += "   - Status at top: `adopted — Option B (dual-layer)` dated 2026-08-08\n";
ch_prompt += "   - Decision log row: Official adoption | owner via agent workflow (Option B)\n";
ch_prompt += "   - Keep A/C as historical alternatives; mark B as ADOPTED\n";
ch_prompt += "2. Edit AGENTS.md: in Two layers section, link to docs/CHARTER-RESEARCH-LAYER.md as adopted charter\n";
ch_prompt += "3. Prepend a short note to results/xau_loop_status.md: charter B adopted; strategy disposition still RESEARCH_IDLE / promote=no\n";
ch_prompt += "4. Write results/xau_charter_adopted.md one-pager restating boundaries (src ↛ research; no live without consent; merge ≠ promote)\n\n";
ch_prompt += "Return ok=true if files updated. summary = charter status line.";

let ch_r = agent(
    ch_prompt,
    #{
        label: "adopt-charter-b",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

if ch_r == () || !ch_r.success || ch_r.output.ok != true {
    complete(#{
        ok: false,
        summary: "Charter adoption failed; abort PR/deploy",
        details: "adopt phase failed",
    });
}

// ---------------------------------------------------------------------------
phase("Draft-PR");
log("Open draft PR research branch → main (do not merge)");

let pr_prompt = "";
pr_prompt += "Repo: " + root + "\n";
pr_prompt += "SAFETY: Open a **draft** PR only. Do NOT merge. Do NOT force-push.\n";
pr_prompt += "gh is authenticated as Trujillofa.\n\n";
pr_prompt += "1. Ensure branch is pushed: git push -u origin HEAD (ordinary push)\n";
pr_prompt += "2. Read results/xau_pr_draft.md for title/body\n";
pr_prompt += "3. Update the draft body if needed to say **Charter Option B is ADOPTED** (not merely recommended)\n";
pr_prompt += "4. Check if a PR already exists for this branch:\n";
pr_prompt += "   gh pr list --head research/algo-trading-btc-gold-forex --state all\n";
pr_prompt += "5. If none open: create draft PR with gh:\n";
pr_prompt += "   gh pr create --draft --base main --head research/algo-trading-btc-gold-forex \\\n";
pr_prompt += "     --title \"...\" --body-file <path>\n";
pr_prompt += "   Write body to a temp file from the suggested markdown in xau_pr_draft.md (include Summary table,\n";
pr_prompt += "   null kills, RESEARCH_IDLE, charter B adopted, open items CSV history + commission).\n";
pr_prompt += "6. If PR already open: update body with gh pr edit if needed; leave draft if still draft\n";
pr_prompt += "7. Record URL in results/xau_pr_opened.md\n\n";
pr_prompt += "Return ok=true if a draft PR URL exists. summary = PR URL + number.";

let pr_r = agent(
    pr_prompt,
    #{
        label: "open-draft-pr",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

// ---------------------------------------------------------------------------
phase("Deploy-bridge");
log("Deploy and compile Mt5ArchBridge v1.22 into Exness prefix");

let dep_prompt = "";
dep_prompt += "Repo: " + root + "\n";
dep_prompt += "SAFETY: Do NOT kill trading terminals unless a script requires it and you warn first.\n";
dep_prompt += "Prefer copy+compile only. Do NOT --live. Do NOT place orders.\n\n";
dep_prompt += "Exness Wine prefix exists: ~/.mt5-exness with MetaTrader 5 EXNESS.\n\n";
dep_prompt += "Deploy Mt5ArchBridge.mq5 v1.22 (with ResolveSymbol):\n";
dep_prompt += "1. Prefer: WINEPREFIX=$HOME/.mt5-exness bash scripts/18-install-forex-indicator.sh  (copies bridge into EXNESS MQL5 tree)\n";
dep_prompt += "   OR manually cp mql5/Mt5ArchBridge.mq5 into:\n";
dep_prompt += "   $HOME/.mt5-exness/drive_c/Program Files/MetaTrader 5 EXNESS/MQL5/Experts/\n";
dep_prompt += "2. Also ensure symlink/generic path gets a copy if used by 06-install-file-bridge:\n";
dep_prompt += "   $HOME/.mt5-exness/drive_c/Program Files/MetaTrader 5/MQL5/Experts/ if that tree exists\n";
dep_prompt += "3. Compile with MetaEditor64 under that prefix, e.g.:\n";
dep_prompt += "   export WINEPREFIX=$HOME/.mt5-exness\n";
dep_prompt += "   wine MetaEditor64.exe /compile:\"C:\\\\Program Files\\\\MetaTrader 5 EXNESS\\\\MQL5\\\\Experts\\\\Mt5ArchBridge.mq5\"\n";
dep_prompt += "   (find actual MetaEditor path; allow ~2 min for wine)\n";
dep_prompt += "4. Confirm .ex5 exists or compile log shows 0 errors. If compile fails, leave source deployed and document failure.\n";
dep_prompt += "5. Optionally also deploy to Vantage (~/.mt5-vantage) the same way since that terminal was used for research — do not restart terminals aggressively.\n";
dep_prompt += "6. Write results/xau_bridge_deploy_exness.md with paths, compile result, and that user must re-attach EA on chart if already running (or restart terminal) to load v1.22\n\n";
dep_prompt += "Return ok=true if source is deployed to Exness Experts (compile success preferred but source-only still ok=true with note).\n";
dep_prompt += "summary = deploy paths + compile status.";

let dep_r = agent(
    dep_prompt,
    #{
        label: "deploy-exness-bridge",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

// ---------------------------------------------------------------------------
phase("Verify");
log("Verify deploy, tests, PR state");

let vf_prompt = "";
vf_prompt += "Repo: " + root + "\n";
vf_prompt += "1. rg -n \"ResolveSymbol|v1.22\" in Exness Experts Mt5ArchBridge.mq5 (Wine path)\n";
vf_prompt += "2. If bridge dir has symbols.json under Exness MQL5/Files/mt5_arch, note size/mtime (may be empty until EA reattached)\n";
vf_prompt += "3. uv run pytest tests/test_cli_unit.py tests/test_xau_pipeline.py -q\n";
vf_prompt += "4. gh pr view --json url,isDraft,state,title (for the PR we opened)\n";
vf_prompt += "5. Append verification block to results/xau_bridge_deploy_exness.md\n\n";
vf_prompt += "Return ok=true if tests pass and PR is draft. summary = tests + PR URL + bridge note.";

let vf_r = agent(
    vf_prompt,
    #{
        label: "verify",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

// ---------------------------------------------------------------------------
phase("Commit-push");
log("Commit charter adoption artifacts and push");

let cm_prompt = "";
cm_prompt += "Repo: " + root + "\n";
cm_prompt += "SAFETY: ordinary push only. No force-push. No merge.\n";
cm_prompt += "Do not commit .omo/ or Wine binaries (.ex5 optional — prefer not to commit Wine artifacts).\n\n";
cm_prompt += "1. git status; stage:\n";
cm_prompt += "   docs/CHARTER-RESEARCH-LAYER.md AGENTS.md results/xau_loop_status.md\n";
cm_prompt += "   results/xau_charter_adopted.md results/xau_pr_opened.md results/xau_pr_draft.md\n";
cm_prompt += "   results/xau_bridge_deploy_exness.md .grok/workflows/xau-charter-pr-bridge.rhai\n";
cm_prompt += "   any other docs touched this run\n";
cm_prompt += "2. Commit: 'docs: adopt dual-layer charter B; draft PR + Exness bridge deploy notes'\n";
cm_prompt += "3. git push origin HEAD\n";
cm_prompt += "4. Write results/xau_next_steps_done.md summarizing charter B, PR URL, bridge deploy, remaining human ops (reattach EA, CSV history, commission)\n\n";
cm_prompt += "Return ok=true if commit+push succeeded. summary = hash + PR URL.";

let cm_r = agent(
    cm_prompt,
    #{
        label: "commit-push",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

// ---------------------------------------------------------------------------
let ch_ok = ch_r != () && ch_r.success && ch_r.output.ok == true;
let pr_ok = pr_r != () && pr_r.success && pr_r.output.ok == true;
let dep_ok = dep_r != () && dep_r.success && dep_r.output.ok == true;
let vf_ok = vf_r != () && vf_r.success && vf_r.output.ok == true;
let cm_ok = cm_r != () && cm_r.success && cm_r.output.ok == true;
let all_ok = ch_ok && pr_ok && dep_ok && vf_ok && cm_ok;

let summary = "charter-pr-bridge: ";
if all_ok {
    summary += "OK";
} else {
    summary += "PARTIAL";
}
if pr_r != () && pr_r.success && pr_r.output.summary != () {
    summary += " — " + pr_r.output.summary;
}
if cm_r != () && cm_r.success && cm_r.output.summary != () {
    summary += " | " + cm_r.output.summary;
}

let details = "";
details += "charter=" + ch_ok.to_string();
details += " pr=" + pr_ok.to_string();
details += " deploy=" + dep_ok.to_string();
details += " verify=" + vf_ok.to_string();
details += " commit=" + cm_ok.to_string();

complete(#{
    ok: all_ok,
    summary: summary,
    details: details,
});
