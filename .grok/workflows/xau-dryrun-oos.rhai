let meta = #{
    name: "xau-dryrun-oos",
    description: "Next recommended XAU action: dry-run live_trader --once (no --live) + fixed-param OOS holdout + summary",
    phases: [
        #{ title: "Prep", detail: "Terminal status and data freshness" },
        #{ title: "DryRun", detail: "live_trader.py --once dry-run only" },
        #{ title: "OOS", detail: "Fixed params holdout backtest" },
        #{ title: "Report", detail: "Write summary artifact" },
    ],
    when_to_use: "After in-sample gates pass; validate dry signal path and OOS before any live trading",
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

phase("Prep");
log("Check Wine MT5 terminal + data freshness (no live orders)");
let prep = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "Goal: prepare for dry-run + OOS. Do NOT place live orders. Do NOT pass --live.\n"
        + "Steps:\n"
        + "1. Run: pgrep -af 'terminal64|wine' | head -20\n"
        + "2. Run: ls -la xauusd_data.csv strategy_params.json; head -2 xauusd_data.csv; tail -2 xauusd_data.csv\n"
        + "3. Run: ./scripts/08-status.sh 2>/dev/null || true; cat results/*account* 2>/dev/null | head -5 || true\n"
        + "4. If terminal64 is NOT running, start it with: nohup bash -c 'cd ~/.mt5-vantage && wine terminal64.exe /portable' >/tmp/mt5-term.log 2>&1 &\n"
        + "   Wait a few seconds and re-check pgrep. Do not kill existing terminal if already up.\n"
        + "5. Optionally refresh export if xauusd_data.csv is older than 24h: bash scripts/export-xau-from-wine-mt5.sh 2>&1 | tail -40\n"
        + "Return ok=true if terminal is up (or started) and CSV+strategy_params exist. Put command outputs in details.",
    #{
        label: "prep-status",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("DryRun");
log("Dry-run live_trader.py --once (never --live)");
let dry = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "CRITICAL SAFETY: run dry-run only. NEVER pass --live. Never send real orders.\n"
        + "Steps:\n"
        + "1. cd to repo root\n"
        + "2. Run: python3 live_trader.py --once 2>&1\n"
        + "   Capture full stdout/stderr and exit code.\n"
        + "3. Interpret result:\n"
        + "   - Exit 0 with signal/sizing path: ok=true\n"
        + "   - Exit 2 with 'MetaTrader5 package not available' + dry sizing demo: ok=true with note that offline sizing worked but MT5 Python package is missing (expected on pure Linux without wine bridge package). Still a valid dry-run for risk math.\n"
        + "   - Crash/unhandled exception: ok=false\n"
        + "4. If MT5 package missing, also run a pure offline signal check:\n"
        + "   python3 -c \"\n"
        + "from live_trader import load_params, size_position\n"
        + "from backtest import load_h1, indicators, simulate\n"
        + "import json\n"
        + "p=load_params()\n"
        + "print('params', p)\n"
        + "d=indicators(load_h1())\n"
        + "m=simulate(d, **{k:v for k,v in p.items() if k in ['mode','rsi_buy','rsi_sell','sl_atr','tp_atr','bb_col','trend_col','use_macd_filter','hours','long_only','risk_pct','cooldown','require_uptrend'] or True})\n"
        + "\" 2>&1 | tail -30\n"
        + "   Prefer a simpler path: python3 -c that loads strategy_params, calls size_position for a sample XAU setup, and prints last H1 bar from xauusd_data.csv.\n"
        + "Return ok, a one-line summary, and full command output in details.",
    #{
        label: "dry-run-once",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("OOS");
log("Fixed-param OOS holdout on chronological split");
let oos = agent(
    "Repo: /home/yderf/Projects/trading/mt5-arch-integration\n"
        + "Goal: out-of-sample holdout backtest with FIXED params from strategy_params.json (no re-optimization).\n"
        + "Do NOT pass --live. Do NOT rewrite strategy_params.json from a full search.\n"
        + "Run this Python script via python3 (inline or temp file under /tmp):\n\n"
        + "```python\n"
        + "import json\n"
        + "from pathlib import Path\n"
        + "import pandas as pd\n"
        + "from backtest import load_h1, indicators, simulate, passes, print_metrics, Metrics\n"
        + "ROOT = Path('/home/yderf/Projects/trading/mt5-arch-integration')\n"
        + "params = json.loads((ROOT/'strategy_params.json').read_text())['params']\n"
        + "if isinstance(params.get('hours'), list):\n"
        + "    params['hours'] = tuple(params['hours']) if params['hours'] else None\n"
        + "# drop keys simulate may not accept\n"
        + "d = indicators(load_h1())\n"
        + "d['time'] = pd.to_datetime(d['time'], utc=True)\n"
        + "t0, t1 = d['time'].min(), d['time'].max()\n"
        + "split = t0 + (t1 - t0) * 0.70\n"
        + "train = d[d['time'] < split].reset_index(drop=True)\n"
        + "test = d[d['time'] >= split].reset_index(drop=True)\n"
        + "print('split', split, 'train_bars', len(train), 'oos_bars', len(test))\n"
        + "print('train_range', train['time'].iloc[0], '->', train['time'].iloc[-1])\n"
        + "print('oos_range', test['time'].iloc[0], '->', test['time'].iloc[-1])\n"
        + "m_is = simulate(train, **params)\n"
        + "m_oos = simulate(test, **params)\n"
        + "print('=== IN-SAMPLE (fixed params) ===')\n"
        + "print_metrics(m_is)\n"
        + "print('gates', passes(m_is))\n"
        + "print('=== OOS HOLDOUT (fixed params) ===')\n"
        + "print_metrics(m_oos)\n"
        + "print('gates', passes(m_oos))\n"
        + "out = {\n"
        + "  'split': str(split),\n"
        + "  'params': params,\n"
        + "  'in_sample': m_is.__dict__,\n"
        + "  'oos': m_oos.__dict__,\n"
        + "  'oos_gates_pass': passes(m_oos),\n"
        + "  'gates': {'pf': 1.5, 'wr': 55.0, 'dd': 10.0},\n"
        + "}\n"
        + "(ROOT/'results'/'xau_oos_holdout.json').write_text(json.dumps(out, indent=2, default=str))\n"
        + "print('Wrote results/xau_oos_holdout.json')\n"
        + "```\n\n"
        + "If simulate kwargs fail (e.g. require_uptrend), inspect simulate signature in backtest.py and pass only accepted kwargs.\n"
        + "Return ok=true if OOS metrics were computed and JSON written (ok may still be true if gates fail — report gate status clearly in summary).\n"
        + "summary must include: OOS net_profit, win_rate, profit_factor, max_drawdown_pct, n_trades, gates_pass.",
    #{
        label: "oos-holdout",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

phase("Report");
log("Synthesize dry-run + OOS into results markdown");
let dry_ok = dry != () && dry.success && dry.output != () && dry.output.ok == true;
let oos_ok = oos != () && oos.success && oos.output != () && oos.output.ok == true;
let prep_ok = prep != () && prep.success && prep.output != () && prep.output.ok == true;

let dry_sum = "dry-run unavailable";
if dry != () && dry.success && dry.output != () && dry.output.summary != () {
    dry_sum = dry.output.summary;
}
let oos_sum = "oos unavailable";
if oos != () && oos.success && oos.output != () && oos.output.summary != () {
    oos_sum = oos.output.summary;
}
let dry_det = "";
if dry != () && dry.success && dry.output != () && dry.output.details != () {
    dry_det = dry.output.details;
}
let oos_det = "";
if oos != () && oos.success && oos.output != () && oos.output.details != () {
    oos_det = oos.output.details;
}
let prep_sum = "prep n/a";
if prep != () && prep.success && prep.output != () && prep.output.summary != () {
    prep_sum = prep.output.summary;
}

let report = agent(
    "Write a concise markdown report for the XAU next-action validation.\n"
        + "Save to: /home/yderf/Projects/trading/mt5-arch-integration/results/xau_dryrun_oos_summary.md\n"
        + "Also copy/write the same content via shell if needed.\n\n"
        + "Use these phase results (do not invent numbers — quote only what is present):\n"
        + "PREP_OK=" + prep_ok.to_string() + " PREP_SUMMARY=" + json_encode(prep_sum) + "\n"
        + "DRY_OK=" + dry_ok.to_string() + " DRY_SUMMARY=" + json_encode(dry_sum) + "\n"
        + "DRY_DETAILS=" + json_encode(dry_det) + "\n"
        + "OOS_OK=" + oos_ok.to_string() + " OOS_SUMMARY=" + json_encode(oos_sum) + "\n"
        + "OOS_DETAILS=" + json_encode(oos_det) + "\n\n"
        + "If results/xau_oos_holdout.json exists, read it and include exact metrics tables.\n"
        + "Report structure:\n"
        + "# XAU dry-run + OOS summary\n"
        + "## Safety\n- Confirmed no --live\n"
        + "## Prep\n## Dry-run live_trader --once\n## OOS holdout (fixed params)\n## Gates\n## Recommended next step\n"
        + "Recommended next step rules:\n"
        + "- If OOS gates pass AND dry-run ok: suggest paper/loop dry monitoring, still no live.\n"
        + "- If OOS gates fail: recommend no live, investigate regime / retrain only on train split.\n"
        + "- If dry-run only offline sizing (no MetaTrader5 package): note bridge gap, keep dry-only.\n"
        + "Return ok=true if the markdown file was written. summary = path + one-line verdict.",
    #{
        label: "write-report",
        capability_mode: "execute",
        cwd: root,
        output_schema: result_schema,
    }
);

let report_ok = report != () && report.success && report.output != () && report.output.ok == true;
let report_sum = "report failed";
if report != () && report.success && report.output != () && report.output.summary != () {
    report_sum = report.output.summary;
}

let all_ok = dry_ok && oos_ok && report_ok;
let scratch = "# XAU dry-run + OOS workflow\n\n"
    + "- prep_ok: " + prep_ok.to_string() + " — " + prep_sum + "\n"
    + "- dry_ok: " + dry_ok.to_string() + " — " + dry_sum + "\n"
    + "- oos_ok: " + oos_ok.to_string() + " — " + oos_sum + "\n"
    + "- report_ok: " + report_ok.to_string() + " — " + report_sum + "\n"
    + "- all_ok: " + all_ok.to_string() + "\n"
    + "- artifact: results/xau_dryrun_oos_summary.md\n"
    + "- oos_json: results/xau_oos_holdout.json\n"
    + "- safety: never used --live\n";

let path = write_scratch_file("xau_dryrun_oos.md", scratch);
log(scratch);

complete(#{
    summary: report_sum,
    all_ok: all_ok,
    dry_ok: dry_ok,
    oos_ok: oos_ok,
    prep_ok: prep_ok,
    report_ok: report_ok,
    scratch: path,
    report_path: "results/xau_dryrun_oos_summary.md",
});
