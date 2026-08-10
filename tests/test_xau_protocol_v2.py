"""Protocol v2.2: normalized OHLC increments, identity k, charter registry."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from xau_charter_protocol import (  # noqa: E402
    CharterError,
    RegistryError,
    _parse_jsonl_strict,
    charter_file_sha256,
    gates_from_charter,
    is_charter_runnable,
    registry_disposition,
    validate_charter,
    write_charter_once,
)
from xau_null_core import (  # noqa: E402
    _null_within_day_return_rotate,
    apply_null_method,
    null_invariants_ok,
    pvalue,
)


def _days_ohlc(n_days: int = 4, hours: range = range(1, 24)) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    rows = []
    price = 2000.0
    for day in range(n_days):
        for hour in hours:
            # realistic small open/prev gaps: open near prev close
            open_px = price * float(np.exp(rng.normal(0, 0.00005)))
            close_px = open_px * float(np.exp(rng.normal(0, 0.002)))
            high_px = max(open_px, close_px) * float(np.exp(abs(rng.normal(0, 0.0003))))
            low_px = min(open_px, close_px) * float(np.exp(-abs(rng.normal(0, 0.0003))))
            price = close_px
            ts = pd.Timestamp(f"2024-06-{3 + day:02d} {hour:02d}:00:00", tz="UTC")
            rows.append(
                {
                    "time": ts,
                    "open": open_px,
                    "high": high_px,
                    "low": low_px,
                    "close": close_px,
                    "spread": 18.0,
                }
            )
    return pd.DataFrame(rows)


def test_write_charter_once_refuses_overwrite(tmp_path: Path):
    p = tmp_path / "2026-08-10_demo_v1.json"
    write_charter_once(p, {"family_id": "demo", "status": "FROZEN"})
    with pytest.raises(CharterError, match="already exists"):
        write_charter_once(p, {"family_id": "demo2"})


def test_tod_charter_restored_byte_sha_and_registry():
    p = ROOT / "results/xau_charters/2026-08-10_tod_london_ny_flat_v1.json"
    # must match freeze commit 664a79c content SHA
    assert charter_file_sha256(p) == (
        "e7cd953f998015bbc9aa5ae23ea7f35c45723f82736a273274f41102bac2f4cf"
    )
    # in-file must NOT carry disposition mutation
    ch = json.loads(p.read_text())
    assert "disposition" not in ch or ch.get("disposition") not in (
        "PROTOCOL_NULL_INVALID",
        "SCREEN_FAIL",
    )
    rec = registry_disposition(charter_file_sha256(p))
    assert rec is not None
    assert rec["disposition"] == "PROTOCOL_NULL_INVALID"
    ok, why = is_charter_runnable(p)
    assert ok is False
    assert "registry" in why or "PROTOCOL" in why


def test_server_hour_v1_superseded_v2_canonical():
    v1 = ROOT / "results/xau_charters/2026-08-10_server_hour_window_flat_v1.json"
    v2 = ROOT / "results/xau_charters/2026-08-10_server_hour_window_flat_v2.json"
    assert charter_file_sha256(v1).startswith("6b5811ee")
    ok1, why1 = is_charter_runnable(v1)
    assert ok1 is False and "SUPERSEDED" in why1
    ch2 = json.loads(v2.read_text())
    assert ch2["protocol_version"] == 2.2
    assert ch2["null"]["method"] == "within_day_ohlc_increment_rotate_v1"
    assert "k∈{0" in ch2["null"]["k_domain"] or "0" in ch2["null"]["k_domain"]
    assert "open_prev_close_gap_multiset" in ch2["null"]["invariants"]
    assert validate_charter(ch2) == []
    # v2 closed SCREEN_FAIL in registry (zero primary passers) — not runnable
    ok2, why2 = is_charter_runnable(v2)
    assert ok2 is False and "SCREEN_FAIL" in why2


def test_session_charter_rejects_noncanonical_null():
    v2 = json.loads(
        (ROOT / "results/xau_charters/2026-08-10_server_hour_window_flat_v2.json").read_text()
    )
    bad = dict(v2)
    bad["null"] = dict(v2["null"])
    bad["null"]["method"] = "global_return_shuffle"
    errs = validate_charter(bad)
    assert any("global_return_shuffle" in e for e in errs)
    assert any("within_day_ohlc_increment_rotate_v1" in e for e in errs)


def test_registry_terminal_is_monotonic(tmp_path: Path):
    reg = tmp_path / "reg.jsonl"
    sha = "abc" * 16
    rows = [
        {"charter_sha256": sha, "disposition": "PROTOCOL_NULL_INVALID"},
        {"charter_sha256": sha, "disposition": "PASS"},
    ]
    reg.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    rec = registry_disposition(sha, path=reg)
    assert rec is not None
    assert rec["disposition"] == "PROTOCOL_NULL_INVALID"


def test_registry_malformed_fails_closed(tmp_path: Path):
    reg = tmp_path / "reg.jsonl"
    reg.write_text("{not json\n")
    with pytest.raises(RegistryError):
        _parse_jsonl_strict(reg)
    with pytest.raises(RegistryError):
        registry_disposition("x", path=reg)


def test_legacy_prior_day_charter_not_deleted():
    p = ROOT / "results/xau_next_design_charter.json"
    assert json.loads(p.read_text())["family_id"] == "prior_day_high_break"


def test_gates_from_charter_soft_provenance():
    ch = json.loads(
        (ROOT / "results/xau_charters/2026-08-10_server_hour_window_flat_v1.json").read_text()
    )
    g = gates_from_charter(ch)
    assert g["soft"]["profit_factor_min"] == 1.1
    assert "exp>=20" not in (g["description"]["soft"] or "")


def test_within_day_v22_preserves_ohlc_continuity_and_gaps():
    raw = _days_ohlc(5)
    # force a non-identity-heavy seed
    rng = np.random.default_rng(99)
    scr = apply_null_method(raw, rng, method="within_day_ohlc_increment_rotate_v1")
    inv = null_invariants_ok(
        raw, scr, method="within_day_ohlc_increment_rotate_v1", entry_hour=13, flat_hour=16
    )
    assert inv["same_length"]
    assert inv["time_unchanged"]
    assert inv["spread_calendar_aligned"]
    assert inv["per_day_bar_count_equal"]
    assert inv["open_prev_close_gap_multiset"]
    assert inv["true_range_prev_multiset"]
    assert inv["within_day_path_continuous"]

    # gap bp distribution must not inflate like v2.1
    def gap_bp(df: pd.DataFrame) -> np.ndarray:
        o = df["open"].to_numpy(float)
        c = df["close"].to_numpy(float)
        day = pd.to_datetime(df["time"], utc=True).dt.strftime("%Y-%m-%d").to_numpy()
        g = []
        for i in range(1, len(df)):
            if day[i] == day[i - 1] and c[i - 1] > 0:
                g.append(abs(o[i] - c[i - 1]) / c[i - 1] * 1e4)
        return np.asarray(g)

    gr, gs = gap_bp(raw), gap_bp(scr)
    # medians should be in the same ballpark (not 0.05 → 13+)
    assert np.median(gs) < np.median(gr) * 3 + 1.0
    assert np.quantile(gs, 0.99) < np.quantile(gr, 0.99) * 3 + 5.0


def test_within_day_identity_k0_recovers_ohlc():
    """k=0 for every day must reproduce original OHLC (identity in support)."""
    raw = _days_ohlc(2)

    class ZeroRng:
        def integers(self, low, high=None):
            if high is None:
                return 0
            return low  # always 0 when low=0

    # Monkeypatch via fixed seed that is not reliable; call internal with forced k
    class R:
        def integers(self, low, high=None):
            return 0 if high is None else low

    scr = _null_within_day_return_rotate(raw, R())  # type: ignore[arg-type]
    for col in ("open", "high", "low", "close"):
        assert np.allclose(
            raw[col].to_numpy(float), scr[col].to_numpy(float), rtol=1e-10, atol=1e-10
        )


def test_within_day_k_domain_includes_zero():
    """Statistical check: over many draws, k=0 occurs for multi-bar days."""
    raw = _days_ohlc(1, hours=range(1, 6))  # 5 bars → k in 0..4
    seen_identity = False
    for seed in range(200):
        scr = apply_null_method(
            raw, np.random.default_rng(seed), method="within_day_ohlc_increment_rotate_v1"
        )
        if np.allclose(raw["close"].to_numpy(float), scr["close"].to_numpy(float)):
            seen_identity = True
            break
    assert seen_identity, "k=0 identity never observed in 200 draws"


def test_day_block_marked_session_invalid():
    raw = _days_ohlc(3)
    scr = apply_null_method(raw, np.random.default_rng(0), method="day_block_shuffle")
    inv = null_invariants_ok(raw, scr, method="day_block_shuffle")
    assert inv.get("protocol_session_valid") is False


def test_pvalue_add_one_resolution():
    assert pvalue([0.0] * 40, 1.0) == pytest.approx(1 / 41)
    assert pvalue([0.0] * 199, 1.0) == pytest.approx(1 / 200)


def test_server_hour_family_simulate_smoke():
    from xau_family_server_hour_window_flat import build_grid, prepare, simulate

    raw = _days_ohlc(10)
    d = prepare(raw)
    g = build_grid()
    assert len(g) == 1
    m = simulate(d, **g[0], spread_col="spread", commission_per_lot=0.0)
    assert m.n_trades >= 0


def test_sealed_fixture_blocks_family_mismatch():
    from xau_sealed_family_cycle import _assert_family_matches_charter

    ch = {"family_id": "server_hour_window_flat"}
    assert _assert_family_matches_charter("server_hour_window_flat", ch) == (
        "server_hour_window_flat"
    )
    with pytest.raises(SystemExit):
        _assert_family_matches_charter("tod_london_ny_flat", ch)


def test_v2_screen_fail_in_registry():
    sha = "26ff7532a4cae730f370d350d39df383e83b01f85e0f5de3e1eac9ae283a464e"
    rec = registry_disposition(sha)
    assert rec is not None
    assert rec["disposition"] == "SCREEN_FAIL"
    assert rec.get("r1_burned") is False
    # original closeout record (may be followed by accounting clarifications)
    from xau_charter_protocol import DISPOSITION_REGISTRY, _parse_jsonl_strict

    rows = [r for r in _parse_jsonl_strict(DISPOSITION_REGISTRY) if r.get("charter_sha256") == sha]
    assert any(r.get("screen_status") == "ZERO_PRIMARY_PASSERS" for r in rows)
    assert any(r.get("p_n_passers_implied") == 1.0 for r in rows)
    assert any(r.get("family_screen_attempt") is True for r in rows)
    assert any(r.get("sealed_null_attempt") is False for r in rows)
    ok, why = is_charter_runnable(
        ROOT / "results/xau_charters/2026-08-10_server_hour_window_flat_v2.json"
    )
    assert ok is False and "SCREEN_FAIL" in why


def test_external_charter_path_refused(tmp_path: Path):
    from xau_charter_protocol import assert_charter_path_for_sealed

    p = tmp_path / "evil.json"
    p.write_text("{}")
    with pytest.raises(CharterError, match="under"):
        assert_charter_path_for_sealed(p)


def test_untracked_charter_refused(tmp_path: Path, monkeypatch):
    """Charter under charters/ but not git-tracked must be refused."""
    from xau_charter_protocol import CHARTERS_DIR, assert_charter_path_for_sealed

    p = CHARTERS_DIR / "_test_untracked_do_not_commit.json"
    p.write_text('{"family_id":"x"}')
    try:
        with pytest.raises(CharterError, match="not git-tracked"):
            assert_charter_path_for_sealed(p)
    finally:
        if p.exists():
            p.unlink()


def test_dirty_registry_in_dispositional_globs():
    from xau_charter_protocol import DISPOSITIONAL_PATH_GLOBS

    assert "results/xau_charter_disposition_registry.jsonl" in DISPOSITIONAL_PATH_GLOBS


def test_screen_fail_zero_passers_accounting(tmp_path: Path):
    """End-to-end: zero primary passers ⇒ executed nulls=0, p_max_pf not_evaluated."""
    import xau_family_null_maxstat as harness

    out = tmp_path / "screen_out"
    out.mkdir()
    # server_hour fixed rule has 0 soft passers on develop (same geometry as v2)
    rc = harness.main(
        [
            "--family",
            "server_hour_window_flat",
            "--n-null",
            "999",
            "--out-dir",
            str(out),
            "--workers",
            "1",
        ]
    )
    assert rc == 0
    report = json.loads((out / "null_maxstat.json").read_text())
    assert report["verdict"]["disposition"] == "SCREEN_FAIL"
    assert report["verdict"].get("screen_status") == "ZERO_PRIMARY_PASSERS"
    assert report["null"]["n_null_planned"] == 999
    assert report["null"]["n_null_executed"] == 0
    assert report["null"]["n_trials"] == 0
    assert report["null"]["p_n_passers"] == 1.0
    assert report["null"]["p_max_pf"] is None
    assert report["null"]["p_max_pf_status"] == "not_evaluated"
    assert report["null"]["p_n_passers_status"] == "implied_1.0_zero_real_passers"
    assert "hits=n_null" in report["verdict"]["reason"] or "(n_null+1)/(n_null+1)" in report[
        "verdict"
    ]["reason"]
    acct = report["attempt_accounting"]
    assert acct["attempt_type"] == "DETERMINISTIC_SCREEN"
    assert acct["family_screen_attempt"] is True
    assert acct["sealed_null_attempt"] is False
    assert acct["null_trials_executed"] == 0
    # harness provenance must match executed, not planned
    assert report["provenance"]["n_null"] == 0
    assert report["provenance"]["n_null_executed"] == 0
    assert report["provenance"]["n_null_planned"] == 999


def test_sealed_wrapper_sources_executed_null_from_report(tmp_path: Path, monkeypatch):
    """Outer provenance/ledger must not invent n_null=999 after screen skip."""
    import xau_sealed_family_cycle as sealed

    out = tmp_path / "run"
    out.mkdir()
    # Fake completed harness report as if screen-fail happened
    report = {
        "verdict": {"disposition": "SCREEN_FAIL", "screen_status": "ZERO_PRIMARY_PASSERS"},
        "null": {
            "base_seed": 1,
            "n_trials": 0,
            "n_null_planned": 999,
            "n_null_executed": 0,
        },
        "attempt_accounting": {
            "attempt_type": "DETERMINISTIC_SCREEN",
            "family_screen_attempt": True,
            "sealed_null_attempt": False,
            "n_null_planned": 999,
            "n_null_executed": 0,
            "null_trials_executed": 0,
        },
    }
    (out / "null_maxstat.json").write_text(json.dumps(report))

    captured: dict = {}

    def fake_build_provenance(**kwargs):
        captured.update(kwargs)
        return {"n_null": kwargs.get("n_null"), "extra": kwargs.get("extra")}

    def fake_append(record, path=None):
        captured["ledger"] = record

    monkeypatch.setattr(sealed, "build_provenance", fake_build_provenance)
    monkeypatch.setattr(sealed, "append_attempt", fake_append)
    monkeypatch.setattr(sealed, "ensure_fresh_run_dir", lambda p: p)
    monkeypatch.setattr(sealed, "run_output_dir", lambda *a, **k: out)
    monkeypatch.setattr(sealed, "assert_charter_path_for_sealed", lambda p: {})
    monkeypatch.setattr(sealed, "assert_clean_dispositional_tree", lambda: {})
    fake_charter = {
        "family_id": "server_hour_window_flat",
        "null": {"method": "within_day_ohlc_increment_rotate_v1", "n_trials": 999},
        "fixed": {
            "costs": {
                "spread_col": "spread",
                "point_size": 0.01,
                "commission_per_lot": 0.0,
                "slippage_points": 0.0,
            }
        },
        "protocol_version": 2.2,
        "thesis_class": "server_hour_window_fixed",
        "rule": {"entry_hour": 13, "intraday_flat": True},
        "gates": {
            "soft": {
                "n_trades_min": 20,
                "profit_factor_min": 1.1,
                "net_profit_gt": 0.0,
            },
            "primary_n_passers": "soft",
        },
        "n_free_knobs": 0,
    }
    monkeypatch.setattr(
        sealed, "is_charter_runnable", lambda p: (True, "ok"), raising=False
    )
    monkeypatch.setattr(sealed, "load_charter", lambda p: fake_charter)
    monkeypatch.setattr(sealed, "validate_charter", lambda c: [])
    monkeypatch.setattr(sealed, "_assert_costs_match_charter", lambda c: {})
    monkeypatch.setattr(sealed, "_run_synthetic_fixture", lambda f, c: {"ok": True})
    monkeypatch.setattr(sealed, "count_attempts", lambda f: 0)
    monkeypatch.setattr(
        sealed.subprocess,
        "run",
        lambda *a, **k: type("R", (), {"returncode": 0})(),
    )

    # Use a path that won't hit registry if is_charter_runnable not patched
    rc = sealed.main(
        [
            "--charter",
            str(tmp_path / "dummy_charter.json"),
            "--family",
            "server_hour_window_flat",
            "--run-id",
            "test_screen",
        ]
    )
    assert rc == 0
    assert captured.get("n_null") == 0
    extra = captured.get("extra") or {}
    assert extra.get("n_null_planned") == 999
    assert extra.get("n_null_executed") == 0
    assert extra.get("attempt_type") == "DETERMINISTIC_SCREEN"
    assert extra.get("sealed_null_attempt") is False
    assert extra.get("r1_burned") is False
    led = captured.get("ledger") or {}
    assert led.get("n_null_executed") == 0
    assert led.get("n_null_planned") == 999
    assert led.get("attempt_type") == "DETERMINISTIC_SCREEN"
    assert led.get("family_screen_attempt") is True
    assert led.get("sealed_null_attempt") is False
