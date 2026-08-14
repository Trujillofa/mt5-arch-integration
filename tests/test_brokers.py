"""Tests for multi-broker profile discovery (shipped mt5_arch.brokers + CLI)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mt5_arch.brokers import (
    brokers_dir,
    list_broker_profiles,
    load_broker_profile,
    parse_broker_env_file,
    repo_root,
)
from mt5_arch.cli import main


def test_repo_root_contains_config_brokers() -> None:
    root = repo_root()
    assert (root / "config" / "brokers").is_dir()
    assert brokers_dir(root) == root / "config" / "brokers"


def test_parse_broker_env_file_strips_export_and_home(tmp_path: Path) -> None:
    p = tmp_path / "sample.env"
    p.write_text(
        "# comment\n"
        "export WINEPREFIX=${HOME}/.mt5-test\n"
        "MT5_LOGIN=12345\n"
        'MT5_SERVER="Broker-Live 1"\n'
        "MT5_PASSWORD=should-not-appear\n"
        "MT5_BACKEND=file\n",
        encoding="utf-8",
    )
    data = parse_broker_env_file(p)
    assert "MT5_PASSWORD" not in data
    assert data["MT5_LOGIN"] == "12345"
    assert data["MT5_SERVER"] == "Broker-Live 1"
    assert data["WINEPREFIX"].endswith("/.mt5-test")
    assert "${HOME}" not in data["WINEPREFIX"]
    assert data["MT5_BACKEND"] == "file"


def test_load_and_list_shipped_broker_profiles() -> None:
    """Drive real config/brokers/*.env files in the repo (not fixtures only)."""
    profiles = list_broker_profiles()
    names = {p.name for p in profiles}
    assert "wsf" in names, "expected config/brokers/wsf.env"
    assert "vantage" in names, "expected config/brokers/vantage.env"
    assert "fpmarkets" in names, "expected config/brokers/fpmarkets.env"

    wsf = load_broker_profile("wsf")
    assert wsf.login == "149736"
    assert wsf.server == "WSFmarkets-Server"
    assert "mt5-wsf" in wsf.wineprefix

    vant = load_broker_profile("vantage")
    assert vant.login == "27496181"
    assert vant.server == "VantageMarkets-Live 5"
    assert "mt5-vantage" in vant.wineprefix

    fpm = load_broker_profile("fpmarkets")
    assert fpm.login == "84076984"
    assert fpm.server == "FPMarketsSC-Live"
    assert "mt5-fpmarkets" in fpm.wineprefix

    # as_exports never includes password keys; Settings reads MT5_BROKER
    exp = vant.as_exports()
    assert "MT5_PASSWORD" not in exp
    assert exp["MT5_SERVER"] == "VantageMarkets-Live 5"
    assert exp["MT5_BROKER"] == "vantage"
    assert exp["BROKER"] == "vantage"


def test_load_missing_profile_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_broker_profile("does-not-exist-broker-xyz")


def test_cli_brokers_lists_profiles(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["brokers"])
    assert code == 0
    out = capsys.readouterr().out
    assert "vantage" in out
    assert "wsf" in out
    assert "27496181" in out
    assert "VantageMarkets-Live 5" in out


def test_cli_brokers_json_one_profile(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["brokers", "vantage", "--json"])
    assert code == 0
    out = capsys.readouterr().out
    assert '"name": "vantage"' in out or '"name":"vantage"' in out.replace(" ", "")
    assert "VantageMarkets-Live 5" in out
    assert "password" not in out.lower() or "MT5_PASSWORD" not in out
