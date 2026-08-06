let meta = #{
    name: "btc-indicator-deep-research",
    description: "Design a BTC-specific MT5 indicator from crypto-agent lessons + market structure",
    when_to_use: "When specifying or implementing BtcTrendPullback / BTC visual indicator for MT5",
    phases: [
        #{ title: "Crypto-Agent", detail: "mine strategies and failed BTC theses" },
        #{ title: "MT5-Context", detail: "platform constraints and existing MQL5 patterns" },
        #{ title: "Market-Structure", detail: "BTC CFD specifics for MT5 retail" },
        #{ title: "Design", detail: "synthesize indicator spec (buffers, logic, non-goals)" },
        #{ title: "Report", detail: "write durable design doc in docs/research" },
    ],
};

let extract_schema = #{
    "type": "object",
    "required": ["summary", "keep", "avoid", "key_paths"],
    "properties": #{
        "summary": #{ "type": "string" },
        "keep": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 20 },
        "avoid": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 20 },
        "indicators_used": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 24 },
        "timeframes": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 12 },
        "key_paths": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 30 },
        "failed_theses": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 12 },
    },
};

let mt5_schema = #{
    "type": "object",
    "required": ["summary", "patterns_to_reuse", "constraints", "buffer_contract_lessons"],
    "properties": #{
        "summary": #{ "type": "string" },
        "patterns_to_reuse": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 16 },
        "constraints": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 16 },
        "buffer_contract_lessons": #{ "type": "string" },
        "do_not_reuse_from_fx": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 12 },
    },
};

let market_schema = #{
    "type": "object",
    "required": ["summary", "session_model", "sizing_notes", "signal_style"],
    "properties": #{
        "summary": #{ "type": "string" },
        "session_model": #{ "type": "string" },
        "sizing_notes": #{ "type": "string" },
        "signal_style": #{ "type": "string" },
        "risks": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 12 },
        "sources": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 12 },
    },
};

let design_schema = #{
    "type": "object",
    "required": ["name", "thesis", "chart_tf", "htf_tf", "plots", "buffers", "entry_logic", "filters", "inputs", "non_goals", "implementation_order"],
    "properties": #{
        "name": #{ "type": "string" },
        "thesis": #{ "type": "string" },
        "chart_tf": #{ "type": "string" },
        "htf_tf": #{ "type": "string" },
        "plots": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 12 },
        "buffers": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 16 },
        "entry_logic": #{ "type": "string" },
        "filters": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 16 },
        "inputs": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 24 },
        "non_goals": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 12 },
        "implementation_order": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 12 },
        "why_not_forex_fib": #{ "type": "string" },
        "logger_compatible": #{ "type": "boolean" },
    },
};

let report_schema = #{
    "type": "object",
    "required": ["ok", "report_path", "indicator_name", "executive_summary", "next_actions"],
    "properties": #{
        "ok": #{ "type": "boolean" },
        "report_path": #{ "type": "string" },
        "indicator_name": #{ "type": "string" },
        "executive_summary": #{ "type": "string" },
        "next_actions": #{ "type": "array", "items": #{ "type": "string" }, "maxItems": 12 },
    },
};

let repo = if args == () { () } else { args.repo };
if repo == () {
    repo = "/home/yderf/Projects/trading/mt5-arch-integration";
}
let crypto_agent = if args == () { () } else { args.crypto_agent };
if crypto_agent == () {
    crypto_agent = "/home/yderf/Projects/trading/crypto-agent";
}
let out_path = if args == () { () } else { args.out_path };
if out_path == () {
    out_path = repo + "/docs/research/BTC-INDICATOR-DESIGN.md";
}

// ---------------------------------------------------------------------------
phase("Crypto-Agent");
// ---------------------------------------------------------------------------
log("Mining crypto-agent for BTC-relevant strategy DNA");

let ca_prompt = "";
ca_prompt += "You are extracting lessons for a NEW MetaTrader 5 visual indicator for BTC CFDs.\n";
ca_prompt += "Repo: " + crypto_agent + " (https://github.com/Trujillofa/crypto-agent)\n";
ca_prompt += "Use read_file/grep/list_dir. Do not invent code that is not in the repo.\n\n";
ca_prompt += "MUST read:\n";
ca_prompt += "1. src/strategy/trend_pullback.py (full entry logic)\n";
ca_prompt += "2. src/features/technical.py (indicator set) and docs/INDICATORS.md\n";
ca_prompt += "3. research/DECISION_ABANDON_BTC_REGIME.md and research/RESEARCH_FINDINGS.md (failures)\n";
ca_prompt += "4. research/mtf_btc_eth_template.yaml and docs/MTF_STRATEGY_GUIDE.md (MTF shape)\n";
ca_prompt += "5. src/strategy/volatility_squeeze.py and panic_block_ma.py (skim entry filters)\n";
ca_prompt += "6. README.md strategy philosophy (research→backtest→paper→live)\n\n";
ca_prompt += "Return JSON:\n";
ca_prompt += "- summary: what actually worked as a visual/structural language for BTC\n";
ca_prompt += "- keep: patterns worth porting to an MT5 indicator (not full Python strategies)\n";
ca_prompt += "- avoid: failed BTC theses (too-rare pullbacks, OHLCV-only regime traps, etc.)\n";
ca_prompt += "- indicators_used: concrete fields (ema_50, atr_pct, ...)\n";
ca_prompt += "- timeframes: e.g. 4h regime + 1h entry\n";
ca_prompt += "- failed_theses: short list from research docs\n";
ca_prompt += "- key_paths: absolute files you used\n";

let ca = agent(ca_prompt, #{
    label: "crypto-agent-mine",
    capability_mode: "read-only",
    agent_type: "explore",
    output_schema: extract_schema,
});

let ca_blob = "{}";
let ca_summary = "crypto-agent mine unavailable";
if ca != () && ca.success && ca.output != () {
    ca_blob = json_encode(ca.output);
    ca_summary = ca.output.summary;
    log("crypto-agent mine OK");
} else {
    log("crypto-agent mine failed");
}

// ---------------------------------------------------------------------------
phase("MT5-Context");
// ---------------------------------------------------------------------------
log("Reading mt5-arch MQL5 patterns and constraints");

let mt5_prompt = "";
mt5_prompt += "Extract MT5 implementation constraints for a BTC indicator in " + repo + ".\n";
mt5_prompt += "Read with tools:\n";
mt5_prompt += "- AGENTS.md (platform boundary: no strategy engine in platform)\n";
mt5_prompt += "- mql5/README.md, mql5/Indicators/ForexHtfPivotsFib.mq5 (buffers, iCustom contract)\n";
mt5_prompt += "- mql5/Include/ForexUtils.mqh (what is FX-specific: sessions, pips)\n";
mt5_prompt += "- mql5/Experts/ForexSignalLogger.mq5 (logger expects signal buffer)\n";
mt5_prompt += "- docs/research/ALGO-TRADING-BTC-GOLD-FOREX.md BTC section\n";
mt5_prompt += "- docs/research/PHASE0-DISCOVERY.md BTC naming (BTCUSD)\n";
mt5_prompt += "- docs/FOREX-MT5-ROADMAP.md observe-first principle\n\n";
mt5_prompt += "Return JSON: summary, patterns_to_reuse (Wine-safe, non-repaint, buffer 7-style),\n";
mt5_prompt += "constraints, buffer_contract_lessons, do_not_reuse_from_fx.\n";

let mt5 = agent(mt5_prompt, #{
    label: "mt5-context",
    capability_mode: "read-only",
    agent_type: "explore",
    output_schema: mt5_schema,
});

let mt5_blob = "{}";
if mt5 != () && mt5.success && mt5.output != () {
    mt5_blob = json_encode(mt5.output);
    log("mt5 context OK");
} else {
    log("mt5 context failed");
}

// ---------------------------------------------------------------------------
phase("Market-Structure");
// ---------------------------------------------------------------------------
log("BTC CFD market structure for indicator design");

let mkt_prompt = "";
mkt_prompt += "Research BTC algo/visual trading on retail MT5 CFDs for indicator design (not HFT).\n";
mkt_prompt += "Use web_search/open_page as needed. Ground in: second-scale file bridge, no true exchange volume,\n";
mkt_prompt += "symbol BTCUSD, ATR-based risk, possible weekend/maintenance gaps.\n";
mkt_prompt += "crypto-agent summary: " + ca_summary + "\n";
mkt_prompt += "Prefer: H1/H4 closed-bar decisions, trend+ATR, avoid FX session pip gates.\n";
mkt_prompt += "Return JSON: summary, session_model, sizing_notes, signal_style, risks[], sources[].\n";

let mkt = agent(mkt_prompt, #{
    label: "btc-market",
    capability_mode: "all",
    agent_type: "general-purpose",
    output_schema: market_schema,
});

let mkt_blob = "{}";
if mkt != () && mkt.success && mkt.output != () {
    mkt_blob = json_encode(mkt.output);
    log("market structure OK");
} else {
    log("market structure failed");
}

// ---------------------------------------------------------------------------
phase("Design");
// ---------------------------------------------------------------------------
log("Synthesizing BTC indicator design");

let design_prompt = "";
design_prompt += "Design ONE MT5 chart indicator tailored for BTCUSD CFDs on this stack.\n";
design_prompt += "It must be visual-first (Wave B observe), logger-compatible (iCustom signal buffer),\n";
design_prompt += "and informed by crypto-agent without porting failed regime-router rarity traps.\n\n";
design_prompt += "CRYPTO-AGENT:\n" + ca_blob + "\n\n";
design_prompt += "MT5:\n" + mt5_blob + "\n\n";
design_prompt += "MARKET:\n" + mkt_blob + "\n\n";
design_prompt += "Hard requirements:\n";
design_prompt += "1. Name suggestion like BtcTrendPullback or BtcHtfTrendAtr\n";
design_prompt += "2. Default chart TF H1; HTF bias H4 (or D1) via iBars/CopyBuffer or multi-series\n";
design_prompt += "3. Core DNA from trend_pullback: EMA50/200 regime, pullback to EMA50, RSI reclaim, ATR% filter\n";
design_prompt += "4. VWAP: on MT5 CFD often weak (tick volume) — either session-anchored approx or optional OFF by default\n";
design_prompt += "5. ATR bands or stop guide lines (price distance, not pips)\n";
design_prompt += "6. Signal buffer index documented for ForexSignalLogger (prefer buffer 7 or clear index)\n";
design_prompt += "7. Non-repaint for markers on closed bars only\n";
design_prompt += "8. Explicitly NOT ForexHtfPivotsFib clone; explain why_not_forex_fib\n";
design_prompt += "9. Non-goals: funding rates, OI, true volume, HFT, OrderSend\n";
design_prompt += "10. implementation_order as checklist for MQL5 author\n";
design_prompt += "Return full design JSON matching schema.\n";

let design = agent(design_prompt, #{
    label: "indicator-design",
    capability_mode: "read-only",
    agent_type: "plan",
    output_schema: design_schema,
});

let design_blob = "{}";
let indicator_name = "BtcTrendPullback";
if design != () && design.success && design.output != () {
    design_blob = json_encode(design.output);
    if design.output.name != () { indicator_name = design.output.name; }
    log("design OK: " + indicator_name);
} else {
    log("design failed");
}

// ---------------------------------------------------------------------------
phase("Report");
// ---------------------------------------------------------------------------
log("Writing " + out_path);

let report_prompt = "";
report_prompt += "Write a durable design memo for implementing a BTC-only MT5 indicator.\n";
report_prompt += "Path (create/overwrite): " + out_path + "\n";
report_prompt += "Use write tools. Parent docs/research/ may already exist.\n\n";
report_prompt += "Include sections:\n";
report_prompt += "1. Title, date 2026-08-04, status Design draft\n";
report_prompt += "2. Executive summary (what to build, what NOT to port from FX Fib)\n";
report_prompt += "3. Lessons from crypto-agent (keep/avoid/failed theses)\n";
report_prompt += "4. MT5 constraints (Wine, logger buffer, platform boundary)\n";
report_prompt += "5. Indicator specification (name, thesis, TFs, plots, buffers table)\n";
report_prompt += "6. Entry/filter logic (pseudocode)\n";
report_prompt += "7. Inputs defaults\n";
report_prompt += "8. Logger / iCustom contract\n";
report_prompt += "9. Implementation order (files under mql5/)\n";
report_prompt += "10. Wave B chart recipe for BTCUSD\n";
report_prompt += "11. Non-goals and open questions\n";
report_prompt += "12. Sources (crypto-agent paths + internal docs)\n\n";
report_prompt += "DESIGN JSON:\n" + design_blob + "\n\n";
report_prompt += "CRYPTO-AGENT:\n" + ca_blob + "\n\n";
report_prompt += "MT5:\n" + mt5_blob + "\n\n";
report_prompt += "MARKET:\n" + mkt_blob + "\n\n";
report_prompt += "Return ok, report_path, indicator_name, executive_summary, next_actions.\n";

let report = agent(report_prompt, #{
    label: "write-design-doc",
    capability_mode: "read-write",
    agent_type: "documentation-writer",
    output_schema: report_schema,
});

let ok = false;
let report_path = out_path;
let executive_summary = "";
let next_actions = [];
if report != () && report.success && report.output != () {
    ok = report.output.ok;
    if report.output.report_path != () { report_path = report.output.report_path; }
    if report.output.indicator_name != () { indicator_name = report.output.indicator_name; }
    if report.output.executive_summary != () { executive_summary = report.output.executive_summary; }
    if report.output.next_actions != () { next_actions = report.output.next_actions; }
}

let body = "# btc-indicator-deep-research\n\n";
body += "ok: " + ok.to_string() + "\n";
body += "indicator: " + indicator_name + "\n";
body += "report: " + report_path + "\n\n";
body += executive_summary + "\n\n## Next\n";
for a in next_actions {
    body += "- [ ] " + a + "\n";
}
let scratch = write_scratch_file("report.md", body);

complete(#{
    ok: ok,
    indicator_name: indicator_name,
    report_path: report_path,
    executive_summary: executive_summary,
    next_actions: next_actions,
    scratch: scratch,
});
