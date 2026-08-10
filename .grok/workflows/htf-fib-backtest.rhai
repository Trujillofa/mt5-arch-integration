let meta = #{
    name: "htf-fib-backtest",
    description: "Install/compile HTF Fib tester EA and run offline + document GUI Strategy Tester steps",
    phases: [
        #{ title: "Build", detail: "Deploy and compile EA + indicator" },
        #{ title: "Offline", detail: "Python surrogate backtest on Dukascopy H1" },
        #{ title: "Report", detail: "Summarize results and GUI tester path" },
    ],
};

phase("Build");
let build = agent(
    "In /home/yderf/Projects/trading/mt5-arch-integration: ensure mql5/Experts/ForexHtfFibTester.mq5 and ForexHtfPivotsFib exist. Run ./scripts/18-install-forex-indicator.sh and ./scripts/19-run-htf-fib-backtest.sh only if WINEPREFIX is set. Report compile status of ForexHtfFibTester.ex5 under the active prefix.",
    #{ label: "build-ea", capability_mode: "execute" }
);

phase("Offline");
let offline = agent(
    "Run offline HTF Fib backtest using ctrader-trading-agent .venv python if needed: scripts/htf_fib_offline_backtest.py on eurusd dukascopy H1 for 2022-2024 with and without --no-rsi-ma-filter. Write JSON under results/. Return key metrics as text.",
    #{ label: "offline-bt", capability_mode: "execute" }
);

phase("Report");
let report = agent(
    "Using build and offline context, write a short markdown summary: how to run ForexHtfFibTester in MT5 Strategy Tester GUI, that Wine headless /config often fails, and offline metrics. Save to results/htf_fib_backtest_summary.md via shell.",
    #{ label: "report", capability_mode: "execute" }
);

complete(#{
    summary: "HTF Fib tester EA + offline backtest workflow",
    build_ok: build.success,
    offline_ok: offline.success,
    report_ok: report.success,
});
