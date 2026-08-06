let meta = #{
    name: "algo-trading-deep-research",
    description: "Deep research on MT5 algo-trading integration for BTC, gold (XAU), and forex majors",
    when_to_use: "When planning multi-asset algo trading on mt5-arch-integration + agent stack",
    phases: [
        #{ title: "Stack-Map", detail: "map platform, agent plan, MQL5, brokers" },
        #{ title: "Asset-Research", detail: "parallel BTC / Gold / Forex majors" },
        #{ title: "Architecture", detail: "integration design across platform and agent" },
        #{ title: "Report", detail: "write durable research doc on branch" },
    ],
};

let stack_schema = #{
    "type": "object",
    "required": ["summary", "platform_capabilities", "agent_gap", "existing_mql5", "brokers", "constraints"],
    "properties": #{
        "summary": #{ "type": "string" },
        "platform_capabilities": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 20 },
        "agent_gap": #{ "type": "string" },
        "existing_mql5": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 20 },
        "brokers": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 12 },
        "constraints": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 16 },
        "key_paths": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 30 },
    },
};

let asset_schema = #{
    "type": "object",
    "required": ["asset", "symbols", "market_structure", "mt5_integration", "strategy_fit", "risk_notes", "recommendations", "open_questions"],
    "properties": #{
        "asset": #{ "type": "string" },
        "symbols": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 12 },
        "market_structure": #{ "type": "string" },
        "mt5_integration": #{ "type": "string" },
        "strategy_fit": #{ "type": "string" },
        "risk_notes": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 12 },
        "recommendations": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 12 },
        "open_questions": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 10 },
        "sources": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 12 },
    },
};

let arch_schema = #{
    "type": "object",
    "required": ["summary", "data_path", "signal_path", "execution_path", "symbol_matrix", "phased_roadmap", "non_goals"],
    "properties": #{
        "summary": #{ "type": "string" },
        "data_path": #{ "type": "string" },
        "signal_path": #{ "type": "string" },
        "execution_path": #{ "type": "string" },
        "symbol_matrix": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 20 },
        "phased_roadmap": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 16 },
        "non_goals": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 12 },
        "risks": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 12 },
    },
};

let report_schema = #{
    "type": "object",
    "required": ["ok", "report_path", "executive_summary", "next_actions"],
    "properties": #{
        "ok": #{ "type": "boolean" },
        "report_path": #{ "type": "string" },
        "executive_summary": #{ "type": "string" },
        "next_actions": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 12 },
        "notes": #{ "type": "string" },
    },
};

let repo = if args == () { () } else { args.repo };
if repo == () {
    repo = "/home/yderf/Projects/trading/mt5-arch-integration";
}
let agent_repo = if args == () { () } else { args.agent_repo };
if agent_repo == () {
    agent_repo = "/home/yderf/Projects/trading/mt5-trading-agent";
}
let ctrader_repo = if args == () { () } else { args.ctrader_repo };
if ctrader_repo == () {
    ctrader_repo = "/home/yderf/Projects/trading/ctrader-trading-agent";
}
let out_path = if args == () { () } else { args.out_path };
if out_path == () {
    out_path = repo + "/docs/research/ALGO-TRADING-BTC-GOLD-FOREX.md";
}

// ---------------------------------------------------------------------------
phase("Stack-Map");
// ---------------------------------------------------------------------------
log("Mapping local MT5 platform + agent plan + existing MQL5");

let stack_prompt = "";
stack_prompt += "You are mapping an existing trading stack for multi-asset algo integration.\n";
stack_prompt += "Use read_file, list_dir, grep. Do NOT invent APIs — quote real paths.\n";
stack_prompt += "Never print passwords or .env secrets.\n\n";
stack_prompt += "Repos (read carefully):\n";
stack_prompt += "1. Platform: " + repo + "\n";
stack_prompt += "   - AGENTS.md, README.md, docs/ARCHITECTURE.md, docs/FOREX-MT5-ROADMAP.md\n";
stack_prompt += "   - docs/MULTI-BROKER-MT5.md, mql5/README.md, src/mt5_arch/*.py\n";
stack_prompt += "   - config/brokers/, scripts/18-install-forex-indicator.sh if present\n";
stack_prompt += "2. Agent plan: " + agent_repo + "/docs/plans/mt5-trading-agent.md and README\n";
stack_prompt += "3. Optional patterns: " + ctrader_repo + "/docs/ARCHITECTURE.md (high-level only)\n\n";
stack_prompt += "Return JSON:\n";
stack_prompt += "- summary: 2-4 sentence stack overview\n";
stack_prompt += "- platform_capabilities: what mt5-arch can do today (CLI, file bridge, RPyC, models)\n";
stack_prompt += "- agent_gap: what mt5-trading-agent still needs vs platform\n";
stack_prompt += "- existing_mql5: indicators/EAs and signal buffer contracts\n";
stack_prompt += "- brokers: known broker profiles (names only)\n";
stack_prompt += "- constraints: AGENTS.md boundaries, Wine/Linux limits, no live orders in research\n";
stack_prompt += "- key_paths: absolute paths you relied on\n";

let stack = agent(stack_prompt, #{
    label: "stack-map",
    capability_mode: "read-only",
    agent_type: "explore",
    output_schema: stack_schema,
});

let stack_summary = "Stack map unavailable";
let stack_blob = "{}";
if stack != () && stack.success && stack.output != () {
    stack_summary = stack.output.summary;
    stack_blob = json_encode(stack.output);
    log("Stack map OK");
} else {
    log("Stack map failed or empty — asset research continues with repo paths only");
}

// ---------------------------------------------------------------------------
phase("Asset-Research");
// ---------------------------------------------------------------------------
log("Parallel research: BTC, Gold, Forex majors");

let common_tail = "";
common_tail += "\nGround every recommendation in the local stack where possible.\n";
common_tail += "Platform repo: " + repo + "\n";
common_tail += "Agent plan: " + agent_repo + "/docs/plans/mt5-trading-agent.md\n";
common_tail += "Stack map (may be partial JSON): " + stack_blob + "\n";
common_tail += "Use web_search/open_page for symbol conventions, session hours, contract sizes, ";
common_tail += "and typical MT5 CFD differences — cite URLs in sources[].\n";
common_tail += "Also read local mql5/ and docs/ with read_file/grep.\n";
common_tail += "Do NOT place trades. Do NOT claim live broker symbol availability without noting it is unverified.\n";
common_tail += "Return structured JSON matching the schema fields exactly.\n";

let btc_prompt = "";
btc_prompt += "Deep-research BTC algo trading via MT5 integration (CFD/crypto symbols on retail MT5).\n";
btc_prompt += "Focus: symbol naming (BTCUSD vs BTCUSD.a etc), 24/7 sessions, spreads/swaps, ";
btc_prompt += "lot sizing vs FX, volatility regimes, data quality under Wine/file-bridge latency, ";
btc_prompt += "which strategies fit (trend, breakout, mean-reversion) and which do NOT (HFT, market-making).\n";
btc_prompt += "Recommend how this platform should expose BTC candles/account/orders to an agent.\n";
btc_prompt += "asset field must be 'BTC'." + common_tail;

let gold_prompt = "";
gold_prompt += "Deep-research GOLD (XAUUSD / gold CFD) algo trading via MT5 integration.\n";
gold_prompt += "Focus: XAUUSD tick size, contract size variations by broker, London/NY session dynamics, ";
gold_prompt += "news sensitivity (NFP, FOMC, CPI), pip/point conventions, stop distances in ATR, ";
gold_prompt += "correlation with DXY and real yields, typical prop-firm constraints on gold.\n";
gold_prompt += "How Fib/HTF pivot style (already in mql5 ForexHtfPivotsFib) may transfer to gold.\n";
gold_prompt += "asset field must be 'GOLD'." + common_tail;

let fx_prompt = "";
fx_prompt += "Deep-research FOREX MAJORS algo trading via MT5 integration.\n";
fx_prompt += "Majors focus: EURUSD, GBPUSD, USDJPY, and optionally AUDUSD/USDCAD/USDCHF/NZDUSD.\n";
fx_prompt += "Focus: session windows (Asia/London/NY), spread gates, rollover, swap, ";
fx_prompt += "existing mql5 ForexHtfPivotsFib + ForexSignalLogger path, buffer contracts, ";
fx_prompt += "bridge of levels to Python (roadmap Wave C), paper-then-live progression.\n";
fx_prompt += "Contrast with porting cTrader session-momentum vs staying MT5-visual-first.\n";
fx_prompt += "asset field must be 'FOREX_MAJORS'." + common_tail;

let asset_jobs = [
    #{
        prompt: btc_prompt,
        label: "research:btc",
        capability_mode: "all",
        agent_type: "general-purpose",
        output_schema: asset_schema,
    },
    #{
        prompt: gold_prompt,
        label: "research:gold",
        capability_mode: "all",
        agent_type: "general-purpose",
        output_schema: asset_schema,
    },
    #{
        prompt: fx_prompt,
        label: "research:forex",
        capability_mode: "all",
        agent_type: "general-purpose",
        output_schema: asset_schema,
    },
];

let asset_results = parallel(asset_jobs);

let asset_sections = [];
let assets_blob = "[";
let asset_ok = 0;
for r in asset_results {
    if r != () && r.success && r.output != () {
        if asset_ok > 0 {
            assets_blob += ", ";
        }
        asset_ok += 1;
        let a = r.output.asset;
        if a == () { a = "unknown"; }
        asset_sections.push(a);
        assets_blob += json_encode(r.output);
    }
}
assets_blob += "]";
log(asset_ok.to_string() + "/3 asset research shards returned");

// ---------------------------------------------------------------------------
phase("Architecture");
// ---------------------------------------------------------------------------
log("Synthesizing integration architecture");

let arch_prompt = "";
arch_prompt += "Design how to use the existing algo-trading integration for BTC, GOLD, and forex majors.\n";
arch_prompt += "You are an architect, not an implementer — produce decisions and a phased roadmap.\n";
arch_prompt += "Read AGENTS.md boundaries: platform stays thin; strategies live in agent repo.\n\n";
arch_prompt += "Stack summary: " + stack_summary + "\n";
arch_prompt += "Full stack JSON: " + stack_blob + "\n";
arch_prompt += "Asset research JSON array: " + assets_blob + "\n\n";
arch_prompt += "Repos to re-check if needed: " + repo + " (docs, mql5, src/mt5_arch) and ";
arch_prompt += agent_repo + "/docs/plans/mt5-trading-agent.md\n\n";
arch_prompt += "Return JSON with:\n";
arch_prompt += "- summary: recommended architecture in 3-6 sentences\n";
arch_prompt += "- data_path: candles/account/symbol-info flow (file bridge vs RPyC vs future REST)\n";
arch_prompt += "- signal_path: MQL5 indicators/logger vs Python strategies vs hybrid\n";
arch_prompt += "- execution_path: paper/live modes, order contract (SL/TP required), risk location\n";
arch_prompt += "- symbol_matrix: strings like 'BTCUSD | priority | notes'\n";
arch_prompt += "- phased_roadmap: ordered next steps (observe → bridge → paper → live)\n";
arch_prompt += "- non_goals: what NOT to build in this platform repo\n";
arch_prompt += "- risks: Wine latency, symbol naming, session/news, prop rules, multi-broker\n";

let arch = agent(arch_prompt, #{
    label: "architecture-synth",
    capability_mode: "read-only",
    agent_type: "plan",
    output_schema: arch_schema,
});

let arch_blob = "{}";
let arch_summary = "Architecture synthesis unavailable";
if arch != () && arch.success && arch.output != () {
    arch_blob = json_encode(arch.output);
    arch_summary = arch.output.summary;
    log("Architecture synthesis OK");
} else {
    log("Architecture synthesis failed");
}

// ---------------------------------------------------------------------------
phase("Report");
// ---------------------------------------------------------------------------
log("Writing research report to " + out_path);

let report_prompt = "";
report_prompt += "Write a durable markdown research report for the git branch research/algo-trading-btc-gold-forex.\n";
report_prompt += "Create/overwrite this exact path: " + out_path + "\n";
report_prompt += "Also ensure parent dir docs/research/ exists.\n";
report_prompt += "Use the write/search_replace tools. Capability is read-write.\n\n";
report_prompt += "Sources of truth (structure the report from these; do not invent features):\n";
report_prompt += "STACK:\n" + stack_blob + "\n\n";
report_prompt += "ASSETS:\n" + assets_blob + "\n\n";
report_prompt += "ARCHITECTURE:\n" + arch_blob + "\n\n";
report_prompt += "Required markdown sections:\n";
report_prompt += "1. Title + date (2026-08-04) + status: Research draft\n";
report_prompt += "2. Executive summary\n";
report_prompt += "3. Stack inventory (platform vs agent)\n";
report_prompt += "4. Asset deep-dives: BTC, Gold, Forex majors (tables where useful)\n";
report_prompt += "5. Recommended integration architecture (diagram in mermaid ok)\n";
report_prompt += "6. Symbol matrix & priority order\n";
report_prompt += "7. Phased roadmap (align with FOREX-MT5-ROADMAP waves where possible)\n";
report_prompt += "8. Risks & open questions\n";
report_prompt += "9. Concrete next actions (checkboxes)\n";
report_prompt += "10. Sources / references\n\n";
report_prompt += "Tone: precise engineering memo, not marketing. Respect AGENTS.md: no full strategy engine in platform repo.\n";
report_prompt += "Return JSON: ok=true if file written, report_path, executive_summary (short), next_actions[], notes.\n";

let report = agent(report_prompt, #{
    label: "write-report",
    capability_mode: "read-write",
    agent_type: "documentation-writer",
    output_schema: report_schema,
});

let ok = false;
let report_path = out_path;
let executive_summary = arch_summary;
let next_actions = [];
let notes = "";
if report != () && report.success && report.output != () {
    ok = report.output.ok;
    if report.output.report_path != () { report_path = report.output.report_path; }
    if report.output.executive_summary != () { executive_summary = report.output.executive_summary; }
    if report.output.next_actions != () { next_actions = report.output.next_actions; }
    if report.output.notes != () { notes = report.output.notes; }
}

let body = "# algo-trading-deep-research result\n\n";
body += "ok: " + ok.to_string() + "\n\n";
body += "report: " + report_path + "\n\n";
body += "## Executive summary\n\n" + executive_summary + "\n\n";
body += "## Assets researched\n\n";
for s in asset_sections {
    body += "- " + s + "\n";
}
body += "\n## Next actions\n\n";
for a in next_actions {
    body += "- [ ] " + a + "\n";
}
if notes != () && notes != "" {
    body += "\n## Notes\n\n" + notes + "\n";
}
let scratch = write_scratch_file("report.md", body);

complete(#{
    ok: ok,
    report_path: report_path,
    executive_summary: executive_summary,
    next_actions: next_actions,
    assets: asset_sections,
    stack_summary: stack_summary,
    scratch: scratch,
    notes: notes,
});
