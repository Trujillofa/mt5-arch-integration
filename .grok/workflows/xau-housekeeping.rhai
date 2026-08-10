let meta = #{
    name: "xau-housekeeping",
    description: "Post-RESEARCH_IDLE housekeeping: Exness bridge symbols, ruff, charter/PR draft, CSV history plan",
    phases: [
        #{ title: "Inventory", detail: "Open items, charter options, large-blob facts" },
        #{ title: "Exness-bridge", detail: "Fix default symbol list / m-suffix select for empty symbols.json" },
        #{ title: "Ruff", detail: "Clean what is safe on research scripts without behavior change" },
        #{ title: "Charter-PR", detail: "Written charter decision + PR body draft; no force-push" },
        #{ title: "CSV-plan", detail: "Plan for 9MB CSV in history; no history rewrite unless user already approved" },
        #{ title: "Commit", detail: "Commit safe code/docs; leave history rewrite unapplied" },
    ],
    when_to_use: "After strategy research is RESEARCH_IDLE; clean platform/research hygiene before PR",
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
phase("Inventory");
log("Inventory open housekeeping items");

let inv_prompt = "";
inv_prompt += "Repo: " + root + "\n";
inv_prompt += "SAFETY: offline docs ok. No --live. No force-push. No git history rewrite in this phase.\n\n";
inv_prompt += "Context: XAU strategy edge research is RESEARCH_IDLE (bb_rsi and Donchian null-killed).\n";
inv_prompt += "Standing open items:\n";
inv_prompt += "1. Charter: platform-only repo now hosts a full research layer on this branch\n";
inv_prompt += "2. xauusd_data.csv ~9.4MB in public git history (grew with spread column)\n";
inv_prompt += "3. Ruff findings in research files (~83 previously)\n";
inv_prompt += "4. Exness bridge empty symbols.json — defaults lack m-suffix (SymbolSelect fails)\n";
inv_prompt += "5. Unstaged AGENTS.md expansion (local) — decide keep/commit\n\n";
inv_prompt += "Tasks:\n";
inv_prompt += "- Read AGENTS.md, CLAUDE.md purpose sections, results/xau_loop_status.md top\n";
inv_prompt += "- du -h xauusd_data.csv; git log --oneline -- xauusd_data.csv | head -15\n";
inv_prompt += "- uv run ruff check backtest.py fetch_data.py live_trader.py scripts/xau_*.py scripts/htf_*.py 2>&1 | tail -40\n";
inv_prompt += "- Read mql5/Mt5ArchBridge.mq5 InpSymbols defaults and SymbolSelect loop\n";
inv_prompt += "- Check config/brokers/ for exness; note if missing\n";
inv_prompt += "- Write results/xau_housekeeping_inventory.md with prioritized actions and risks\n\n";
inv_prompt += "Return ok=true if inventory written. summary = top 3 actions.";

let inv_r = agent(
    inv_prompt,
    #{
        label: "inventory",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

// ---------------------------------------------------------------------------
phase("Exness-bridge");
log("Fix Mt5ArchBridge symbol defaults / m-suffix selection");

let ex_prompt = "";
ex_prompt += "Repo: " + root + "\n";
ex_prompt += "SAFETY: edit MQL5 source only in repo. Do NOT require Wine compile for this phase unless trivial.\n";
ex_prompt += "Do NOT kill terminals. Do NOT --live.\n\n";
ex_prompt += "Problem: Exness (and other raw/m brokers) use symbols like EURUSDm / XAUUSDm.\n";
ex_prompt += "Mt5ArchBridge.mq5 default InpSymbols = EURUSD,GBPUSD,... without m, so SymbolSelect fails and symbols.json is empty.\n\n";
ex_prompt += "Implement a robust fix in mql5/Mt5ArchBridge.mq5:\n";
ex_prompt += "1. Add a helper that tries SymbolSelect on bare name, then common suffixes: m, .r, .m, #, pro (pick a short safe list).\n";
ex_prompt += "2. Use it wherever SymbolSelect is called for InpSymbols list and for InpHistorySymbol dump path.\n";
ex_prompt += "3. Expand default InpSymbols to include common m variants OR document that helper makes bare names work.\n";
ex_prompt += "   Prefer helper over a huge default string so one chart input still works across brokers.\n";
ex_prompt += "4. When writing symbols.json, write the *resolved* broker symbol name that selected successfully.\n";
ex_prompt += "5. Bump EA version comment/string if one exists (e.g. v1.21 → v1.22).\n";
ex_prompt += "6. Update mql5/README.md briefly if it documents the symbol list.\n";
ex_prompt += "7. Do not deploy to Wine unless scripts/18 is safe and user path is clear — source fix is enough.\n\n";
ex_prompt += "Return ok=true if EA source compiles cleanly as MQL5 (syntax review) and change is documented.\n";
ex_prompt += "summary = what changed.";

let ex_r = agent(
    ex_prompt,
    #{
        label: "exness-symbols",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

// ---------------------------------------------------------------------------
phase("Ruff");
log("Ruff-clean research scripts where safe");

let rf_prompt = "";
rf_prompt += "Repo: " + root + "\n";
rf_prompt += "SAFETY: no behavior changes. Prefer ruff --fix for auto-safe fixes only.\n\n";
rf_prompt += "1. Run: uv run ruff check backtest.py fetch_data.py live_trader.py scripts --statistics 2>&1 | tail -50\n";
rf_prompt += "2. Apply: uv run ruff check --fix backtest.py fetch_data.py live_trader.py scripts 2>&1 | tail -30\n";
rf_prompt += "   If some codes are unsafe (e.g. need human judgment), leave them and list them.\n";
rf_prompt += "3. Re-run ruff; also uv run ruff check src tests (platform must stay clean).\n";
rf_prompt += "4. uv run pytest tests/test_xau_pipeline.py tests/test_cli_unit.py -q\n";
rf_prompt += "5. Note remaining count in results/xau_housekeeping_ruff.md\n\n";
rf_prompt += "Do not expand scope to rewrite logic. Return ok=true if platform ruff clean and tests pass.\n";
rf_prompt += "summary = fixed vs remaining counts.";

let rf_r = agent(
    rf_prompt,
    #{
        label: "ruff-research",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

// ---------------------------------------------------------------------------
phase("Charter-PR");
log("Draft charter decision and PR body — no merge, no force-push");

let ch_prompt = "";
ch_prompt += "Repo: " + root + "\n";
ch_prompt += "SAFETY: Do NOT open a PR with gh unless the draft is clearly ready AND branch is pushed.\n";
ch_prompt += "You MAY write docs/CHARTER-RESEARCH-LAYER.md and a PR body markdown under results/.\n";
ch_prompt += "Do NOT merge. Do NOT force-push. Prefer drafting over auto-gh-pr if charter is a product decision.\n\n";
ch_prompt += "Write docs/CHARTER-RESEARCH-LAYER.md with three options and a recommended default:\n";
ch_prompt += "A) Keep research offline-only on this branch; never merge to main; platform AGENTS.md stays pure\n";
ch_prompt += "B) Explicit dual-layer charter (platform + offline research) and allow merge with clear boundaries\n";
ch_prompt += "C) Split research into a separate repo later; strip research from main forever\n";
ch_prompt += "Recommend B or A based on current branch reality (research already large; promote=no).\n";
ch_prompt += "Include: src/mt5_arch must not import research; no live from research without consent; RESEARCH_IDLE status.\n\n";
ch_prompt += "Also write results/xau_pr_draft.md with PR title/body for the research branch summarizing:\n";
ch_prompt += "- platform bridge spread dump, costs, null kills (bb_rsi + Donchian), RESEARCH_IDLE\n";
ch_prompt += "- what is NOT claimed (no promote, no live)\n";
ch_prompt += "- open: CSV history, charter choice, commission still unmeasured\n\n";
ch_prompt += "If AGENTS.md local expansion is good and matches CLAUDE.md two-layer story, include it in the planned commit list.\n";
ch_prompt += "Return ok=true if both docs written. summary = recommended charter option.";

let ch_r = agent(
    ch_prompt,
    #{
        label: "charter-pr-draft",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

// ---------------------------------------------------------------------------
phase("CSV-plan");
log("Plan CSV history handling — do not rewrite history");

let csv_prompt = "";
csv_prompt += "Repo: " + root + "\n";
csv_prompt += "SAFETY: CRITICAL — do NOT run git filter-repo, BFG, force-push, or delete history.\n";
csv_prompt += "Only document options and optionally add .gitignore / fetch instructions for future clones.\n\n";
csv_prompt += "Facts: xauusd_data.csv ~9.4MB tracked; tests require it for xau pipeline; branch already public with history.\n\n";
csv_prompt += "Write results/xau_csv_history_plan.md covering:\n";
csv_prompt += "1. Status quo cost (clone size)\n";
csv_prompt += "2. Options ranked: (a) leave it, (b) Git LFS going forward, (c) gitignore + fetch_data.py required + strip from future commits only,\n";
csv_prompt += "   (d) full history rewrite (needs explicit human + force-push approval — mark BLOCKED)\n";
csv_prompt += "3. Recommended path that does NOT need force-push now\n";
csv_prompt += "4. Exact commands the human would run later if they choose rewrite (documented only)\n";
csv_prompt += "5. Whether test_xau_pipeline should skip-if-missing CSV (pros/cons) — implement only if clearly better and small\n\n";
csv_prompt += "If a tiny non-destructive improvement helps (e.g. note in README), do it. No history rewrite.\n";
csv_prompt += "Return ok=true if plan written. summary = recommended option.";

let csv_r = agent(
    csv_prompt,
    #{
        label: "csv-plan",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

// ---------------------------------------------------------------------------
phase("Commit");
log("Commit safe housekeeping; push only ordinary commits if clean");

let cm_prompt = "";
cm_prompt += "Repo: " + root + "\n";
cm_prompt += "SAFETY: No force-push. No history rewrite. Do not commit .omo/ or secrets.\n\n";
cm_prompt += "1. git status; review diffs\n";
cm_prompt += "2. Stage safe housekeeping files only:\n";
cm_prompt += "   - mql5/Mt5ArchBridge.mq5 (+ README if touched)\n";
cm_prompt += "   - ruff-fixed python if any\n";
cm_prompt += "   - docs/CHARTER-RESEARCH-LAYER.md\n";
cm_prompt += "   - results/xau_housekeeping_*.md results/xau_pr_draft.md results/xau_csv_history_plan.md\n";
cm_prompt += "   - AGENTS.md if the expansion is coherent\n";
cm_prompt += "   - .grok/workflows/xau-housekeeping.rhai\n";
cm_prompt += "   - README notes if added\n";
cm_prompt += "3. Commit with a complete-sentence message (HEREDOC). One or two logical commits max.\n";
cm_prompt += "4. Push to origin HEAD with ordinary git push (NOT --force). User asked for housekeeping on this branch.\n";
cm_prompt += "5. Write results/xau_housekeeping_summary.md: what shipped, what is BLOCKED (history rewrite), charter rec, next human decisions.\n";
cm_prompt += "6. uv run pytest tests/test_cli_unit.py tests/test_xau_pipeline.py -q\n\n";
cm_prompt += "Return ok=true if commit(+push if succeeded) done and summary written.\n";
cm_prompt += "summary = commit hash(es) + blocked items.";

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
let inv_ok = inv_r != () && inv_r.success && inv_r.output.ok == true;
let ex_ok = ex_r != () && ex_r.success && ex_r.output.ok == true;
let rf_ok = rf_r != () && rf_r.success && rf_r.output.ok == true;
let ch_ok = ch_r != () && ch_r.success && ch_r.output.ok == true;
let csv_ok = csv_r != () && csv_r.success && csv_r.output.ok == true;
let cm_ok = cm_r != () && cm_r.success && cm_r.output.ok == true;

let all_ok = inv_ok && ex_ok && rf_ok && ch_ok && csv_ok && cm_ok;

let summary = "housekeeping: ";
if all_ok {
    summary += "OK";
} else {
    summary += "PARTIAL";
}
if cm_r != () && cm_r.success && cm_r.output.summary != () {
    summary += " — " + cm_r.output.summary;
}

let details = "";
details += "inv=" + inv_ok.to_string();
details += " exness=" + ex_ok.to_string();
details += " ruff=" + rf_ok.to_string();
details += " charter=" + ch_ok.to_string();
details += " csv=" + csv_ok.to_string();
details += " commit=" + cm_ok.to_string();

complete(#{
    ok: all_ok,
    summary: summary,
    details: details,
});
