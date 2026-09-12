"""XTIUSD is canonical; vantage maps CL-OIL; wsf stays fail-closed."""

from __future__ import annotations

import pytest

from mt5_arch.symbol_registry import SymbolRegistryError, load_registry, resolve


def test_xtiusd_vantage_uso_usd_wsf_unmapped():
    reg = load_registry()
    assert "XTIUSD" in reg.canonical
    assert resolve(reg, "vantage", "XTIUSD").broker_symbol == "CL-OIL"
    assert resolve(reg, "vantage", "CL-OIL").canonical == "XTIUSD"
    with pytest.raises(SymbolRegistryError, match="no mapping"):
        resolve(reg, "wsf", "XTIUSD")
