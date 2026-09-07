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
CONTEXT = DESK / "src" / "lib" / "desk-context.tsx"
GUARDS_UNIT = ROOT / "tests" / "test_desk_live_order_guards.ts"


def test_http_budget_is_bounded_and_shared() -> None:
    guards = GUARDS.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    wine = WINE.read_text(encoding="utf-8")
    assert "LIVE_ORDER_HTTP_BUDGET_MS = 70_000" in guards
    assert "WINE_ONESHOT_BUDGET_MS = 50_000" in guards
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
    assert 'NEOMAA_EXPECTED_SERVER = "Neomaaa-Live"' in neomaa
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
    assert "AbortSignal.timeout(LIVE_ORDER_CLIENT_BUDGET_MS)" in text
    assert "client deadline — live order route returned no JSON" in text


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
    assert "oneshotChartSymbol" in runner
    assert "isUs30Family(parsed.symbol)" in runner
    assert "TRADE_ACTION_PENDING" in mql
    assert "ORDER_TYPE_BUY_LIMIT" in mql
    assert "TRADE_ACTION_REMOVE" in mql
    assert "TRADE_ACTION_PENDING" in wsf
    assert "ORDER_TYPE_BUY_LIMIT" in wsf
    assert "use_volume_min" in runner


def test_guards_node_unit() -> None:
    result = subprocess.run(
        ["node", "--experimental-strip-types", str(GUARDS_UNIT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
