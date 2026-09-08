"""Contract: Seven Desk live orders fail closed and cannot hang HTTP."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESK = ROOT / "apps" / "seven-desk"
RUNNER = DESK / "src" / "lib" / "live-order" / "runner.ts"
GUARDS = DESK / "src" / "lib" / "live-order" / "guards.ts"
WINE = DESK / "src" / "lib" / "live-order" / "wine-oneshot.ts"
MQL = DESK / "mql5" / "DeskLiveOrder.mq5"
WSF_MQL = DESK / "mql5" / "WsfDeskLiveOrder.mq5"
TYPES = DESK / "src" / "lib" / "alphacapital" / "types.ts"
NEOMAA_TYPES = DESK / "src" / "lib" / "neomaa" / "types.ts"
WSF_LIVE = DESK / "src" / "lib" / "wsf" / "live-order.ts"
WSF_FILE = DESK / "src" / "lib" / "wsf" / "mt5-file-backend.ts"
CONTEXT = DESK / "src" / "lib" / "desk-context.tsx"
GUARDS_UNIT = ROOT / "tests" / "test_desk_live_order_guards.ts"


def test_http_budget_is_bounded_and_shared() -> None:
    guards = GUARDS.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    wine = WINE.read_text(encoding="utf-8")
    assert "LIVE_ORDER_HTTP_BUDGET_MS = 70_000" in guards
    assert "WINE_ONESHOT_BUDGET_MS = 50_000" in guards
    assert "EA_ORDER_BUDGET_MS = 12_000" in guards
    assert "not falling back to wine one-shot" in guards
    assert "withDeadline" in guards
    assert "LIVE_ORDER_HTTP_BUDGET_MS" in runner
    assert "runWineUntil" in runner
    assert 'spawnSync("wine", ["./terminal64.exe"' not in runner
    assert "180000" not in runner
    assert "waitQuotesOrFresh" not in runner
    assert "child_process" in wine
    assert "onAbort" in wine


def test_alpha_fx_rewrites_eurusd_pro() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    guards = GUARDS.read_text(encoding="utf-8")
    mql = MQL.read_text(encoding="utf-8")
    assert "quotesPathMatchesSymbol" in runner
    assert "oneshotChartSymbol(firm.id, parsed.symbol)" in runner
    assert 'return "EURUSD.pro"' in guards
    assert 'SymbolSelect("EURUSD.pro"' in mql
    assert 'symbol = "EURUSD.pro"' in mql


def test_alpha_startup_server_is_acgmarkets_main() -> None:
    types = TYPES.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    assert 'ALPHACAPITAL_EXPECTED_SERVER = "ACGMarkets-Main"' in types
    assert "resolveStartupServer(identity.server, firm.server, firm.needle)" in runner
    assert "Server=${server}" in runner
    assert "Server=${firm.server}" not in runner


def test_disconnected_bridge_fails_closed_before_wine() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    wsf = WSF_LIVE.read_text(encoding="utf-8")
    neomaa = NEOMAA_TYPES.read_text(encoding="utf-8")
    assert "identity.terminalConnected === false" in runner
    assert "disconnectedOrderReason(firm.id, identity.server)" in runner
    assert "refusing OrderSend" in runner
    assert "identity.terminalConnected === false" in wsf
    assert "parseBridgeReadonly" in wsf
    assert 'NEOMAA_EXPECTED_SERVER = "Neomaaa-global"' in neomaa
    assert 'NEOMAA_LIVE_CONFIRM = "NEOMAA-7745107"' in neomaa


def test_result_json_must_match_request_id() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    assert "resultMatchesRequest" in runner
    assert "different request_id" in runner
    assert "tryReadMatchingResult" in runner


def test_orphan_request_is_swept_or_fail_closed() -> None:
    guards = GUARDS.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    mql = MQL.read_text(encoding="utf-8")
    assert "LIVE_ORDER_REQUEST_TTL_MS = 90_000" in guards
    assert "classifyOrphanRequest" in guards
    assert "inspectOrphanRequest" in runner
    assert 'orphan.class === "in_flight"' in runner
    assert "inFlightOrphanReason" in runner
    assert "issued_at=" in runner
    assert "dropBridgeFiles([...requestCandidates(paths), ...claimCandidates(paths)])" in runner
    assert "AlreadyClaimed" in mql
    assert "stale desk_live_order_request" in mql
    assert "REQUEST_TTL_SEC" in mql
    assert "WriteClaim" in mql


def test_mql_requires_terminal_connected_and_caps_waits() -> None:
    desk = MQL.read_text(encoding="utf-8")
    wsf = WSF_MQL.read_text(encoding="utf-8")
    assert "WaitConnected(20000)" in desk
    assert "WaitSymbolReady(symbol, 20000)" in desk
    assert "WaitConnected(20000)" in wsf
    assert "return (g_expect_login > 0 && AccountInfoInteger(ACCOUNT_LOGIN) == g_expect_login)" not in desk
    assert "return (AccountInfoInteger(ACCOUNT_LOGIN) == EXPECT_LOGIN)" not in wsf
    assert "return false;" in desk
    assert "TERMINAL_CONNECTED" in desk


def test_order_routes_max_duration_is_90() -> None:
    routes = list((DESK / "src" / "app" / "api").rglob("order/**/route.ts"))
    assert routes
    for path in routes:
        text = path.read_text(encoding="utf-8")
        assert "maxDuration = 90" in text, path
        assert "maxDuration = 180" not in text, path


def test_client_fetch_has_abort_deadline() -> None:
    text = CONTEXT.read_text(encoding="utf-8")
    assert "AbortSignal.timeout(EA_ORDER_CLIENT_BUDGET_MS)" in text
    assert "client deadline — live order route returned no JSON" in text


def test_ea_path_is_primary_and_lots_are_firm_defaults() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    firms = (DESK / "src" / "lib" / "firms.ts").read_text(encoding="utf-8")
    ticket = (DESK / "src" / "components" / "desk" / "trade-ticket.tsx").read_text(
        encoding="utf-8"
    )
    ea = (ROOT / "mql5" / "Mt5ArchBridge.mq5").read_text(encoding="utf-8")
    include = (ROOT / "mql5" / "Include" / "DeskOrderBridge.mqh").read_text(encoding="utf-8")
    assert "DeskOrderProcessIfRequested" in ea
    assert "ORDER_TYPE_BUY_LIMIT" in include
    assert "DESK_LIMIT_OFFSET_POINTS 50" in include
    assert "not falling back to wine one-shot" in runner
    assert "eaNotReadyReason" in runner
    assert "readHeartbeatReadonly" in runner
    assert "parseBridgeReadonly" in runner
    assert "read-only bridge" in GUARDS.read_text(encoding="utf-8")
    assert "DEFAULT_DESK_LOTS = 1.4" in firms
    assert "FUNDEDNEXT_DEFAULT_LOTS = 0.35" in firms
    assert "FUNDINGPIPS_DEFAULT_LOTS = 0.8" in firms
    assert "Buy limit" in ticket
    assert "Sell limit" in ticket
    assert "Buy stop" in ticket
    assert "Sell stop" in ticket
    assert "submit(\"buy\")" in ticket
    assert "submit(\"sell\")" in ticket
    assert "ORDER_TYPE_BUY_STOP" in include
    assert "ORDER_TYPE_SELL_STOP" in include
    assert "TRADE_ACTION_SLTP" in include
    assert 'g_desk_action == "modify"' in include
    resolver = include[
        include.index("ulong DeskOrdResolvePositionTicket") : include.index("bool DeskOrdIsNetting")
    ]
    assert "if(g_desk_ticket > 0)" in resolver
    assert resolver.index("return 0;") < resolver.index("DeskOrdFindPosition")
    snapshots = (ROOT / "mql5" / "Include" / "FileBridgeSnapshots.mqh").read_text(
        encoding="utf-8"
    )
    assert "POSITION_MAGIC" in snapshots


def test_live_is_not_the_default() -> None:
    guards = GUARDS.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    assert "live must be true — paper is the default" in guards
    assert "body.live !== true" in guards
    assert "parseLiveOrderRequest" in runner


def test_us30_pending_contract_is_opt_in() -> None:
    guards = GUARDS.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    mql = MQL.read_text(encoding="utf-8")
    wsf = WSF_MQL.read_text(encoding="utf-8")
    assert "volume_confirm" in guards
    assert "LIVE_ORDER_VOLUME_HARD_MAX = 10" in guards
    assert "US30_SELECT_VARIANTS" in guards
    assert "DJ30.c" in guards
    assert "us30SelectVariantsForFirm" in guards
    assert "WSF_US30_PREFERRED" in guards
    assert '"DJ30.c"' in mql
    assert '"DJ30.c"' in wsf
    assert wsf.index('"DJ30.c"') < wsf.index('"US30.cash"')
    wsf_file = WSF_FILE.read_text(encoding="utf-8")
    assert "orders.json is OrdersTotal" in wsf_file
    assert "positions.json is PositionsTotal" in wsf_file
    assert "Pending orders are not exported" not in wsf_file
    assert "oneshotChartSymbol" in runner
    assert "isUs30Family(parsed.symbol)" in runner
    assert "TRADE_ACTION_PENDING" in mql
    assert "ORDER_TYPE_BUY_LIMIT" in mql
    assert "TRADE_ACTION_REMOVE" in mql
    assert "TRADE_ACTION_PENDING" in wsf
    assert "ORDER_TYPE_BUY_LIMIT" in wsf
    assert "use_volume_min" in runner


FANOUT_UNIT = ROOT / "tests" / "test_desk_copy_fanout.ts"
FANOUT_ALIAS = ROOT / "tests" / "desk-alias-register.mjs"

CLIENT_NO_ENV = [
    DESK / "src" / "lib" / "copy-engine.ts",
    DESK / "src" / "lib" / "copy-fanout.ts",
    DESK / "src" / "lib" / "desk-magic.ts",
    DESK / "src" / "lib" / "bridge-orders.ts",
    DESK / "src" / "lib" / "desk-context.tsx",
    DESK / "src" / "lib" / "desk-store.ts",
    DESK / "src" / "lib" / "use-live-probe-poll.ts",
    DESK / "src" / "components" / "desk" / "trade-ticket.tsx",
    DESK / "src" / "components" / "desk" / "blotter-table.tsx",
    DESK / "src" / "components" / "desk" / "positions-panel.tsx",
    DESK / "src" / "components" / "desk" / "pending-orders-block.tsx",
]


def test_client_modules_do_not_import_env() -> None:
    for path in CLIENT_NO_ENV:
        text = path.read_text(encoding="utf-8")
        assert '/env"' not in text, path
        assert "/env'" not in text, path


def test_confirm_tokens_unchanged() -> None:
    assert 'FTMO_LIVE_CONFIRM = "FTMO-541163357"' in (DESK / "src" / "lib" / "ftmo" / "types.ts").read_text()
    assert 'WSF_LIVE_CONFIRM = "WSF-149736"' in (DESK / "src" / "lib" / "wsf" / "constants.ts").read_text()
    assert 'FUNDEDNEXT_LIVE_CONFIRM = "FN-13981906"' in (DESK / "src" / "lib" / "fundednext" / "types.ts").read_text()
    assert 'FUNDINGPIPS_LIVE_CONFIRM = "FUNDINGPIPS-11669306"' in (
        DESK / "src" / "lib" / "fundingpips" / "types.ts"
    ).read_text()
    assert 'FORTRADERS_LIVE_CONFIRM = "FORTRADERS-737150"' in (
        DESK / "src" / "lib" / "fortraders" / "types.ts"
    ).read_text()
    assert 'NEOMAA_LIVE_CONFIRM = "NEOMAA-7745107"' in (DESK / "src" / "lib" / "neomaa" / "types.ts").read_text()
    assert 'ALPHACAPITAL_LIVE_CONFIRM = "ACG-2765247"' in (
        DESK / "src" / "lib" / "alphacapital" / "types.ts"
    ).read_text()


def test_fanout_skips_alpha_and_confirms_size() -> None:
    fanout = (DESK / "src" / "lib" / "copy-fanout.ts").read_text(encoding="utf-8")
    context = CONTEXT.read_text(encoding="utf-8")
    engine = (DESK / "src" / "lib" / "copy-engine.ts").read_text(encoding="utf-8")
    assert 'COPY_FANOUT_SKIP = new Set<LiveBroker>(["alphacapital"])' in fanout
    assert "needsSizeConfirm" in fanout
    assert "Promise.all" in context
    assert "alpha capital is fetch-only — not copied" in engine
    assert "alpha capital is fetch-only — not copied" in context
    assert 'httpAction: "send"' in engine
    assert 'httpAction: row.livePending ? "cancel" : "close"' in context


def test_flatten_bar_is_always_visible() -> None:
    terminal = (DESK / "src" / "components" / "desk" / "terminal.tsx").read_text(encoding="utf-8")
    bar = (DESK / "src" / "components" / "desk" / "flatten-bar.tsx").read_text(encoding="utf-8")
    engine = (DESK / "src" / "lib" / "copy-engine.ts").read_text(encoding="utf-8")
    assert "FlattenBar" in terminal
    assert "flattenAll" not in terminal
    assert 'state.positions.length > 0' not in bar
    assert "Close positions" in bar
    assert "cancel pendings" in bar
    assert "min-h-11" in bar
    assert "fixed inset-x-0 bottom-0" in bar
    assert "describeFlattenTargets" in engine
    assert "isUs30Family" in engine
    assert "isBrokerLeftover" in engine
    assert "upsertSnapshotPositions" in engine
    panel = (DESK / "src" / "components" / "desk" / "positions-panel.tsx").read_text(
        encoding="utf-8"
    )
    assert "Set SL/TP" in panel
    assert "min-h-11" in panel
    assert "leftover" in panel
    assert "modifyPosition" in CONTEXT.read_text(encoding="utf-8")
    assert "alphaModifyBlocked" in GUARDS.read_text(encoding="utf-8")
    assert "MIN_DESK_MODIFY_VERSION = [1, 27]" in GUARDS.read_text(encoding="utf-8")


def test_guards_node_unit() -> None:
    result = subprocess.run(
        ["node", "--experimental-strip-types", str(GUARDS_UNIT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_copy_fanout_node_unit() -> None:
    result = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            "--import",
            str(FANOUT_ALIAS),
            str(FANOUT_UNIT),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
