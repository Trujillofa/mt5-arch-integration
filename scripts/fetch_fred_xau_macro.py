#!/usr/bin/env python3
"""Fetch a small FRED daily panel for XAU real-yield research.

Reads ``FRED_API_KEY`` from the environment or worktree ``.env``.
Never prints the key. Local research cache only. Attribution: FRED / St. Louis Fed.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
OUT = _ROOT / "results" / "xau_exog_beta" / "data" / "fred"
START = "2018-01-01"
SERIES = {
    "DFII10": "10Y TIPS / real yield (primary)",
    "DGS10": "nominal 10Y",
    "T10YIE": "10Y breakeven inflation",
    "DTWEXBGS": "broad trade-weighted USD",
    "DFII5": "5Y TIPS / real yield (robustness store only)",
}
BASE = "https://api.stlouisfed.org/fred/series/observations"


def _load_key() -> str:
    key = os.environ.get("FRED_API_KEY", "").strip()
    if key:
        return key
    env_path = _ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            if line.startswith("FRED_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("FRED_API_KEY missing (set env or worktree .env)")


def _fetch(series_id: str, key: str) -> dict:
    q = urllib.parse.urlencode(
        {
            "series_id": series_id,
            "api_key": key,
            "file_type": "json",
            "observation_start": START,
        }
    )
    url = f"{BASE}?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "mt5-arch-xau-research/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"FRED HTTP {exc.code} for {series_id}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"FRED network error for {series_id}: {exc.reason}") from exc
    if "observations" not in payload:
        raise SystemExit(f"FRED unexpected payload for {series_id} (no observations)")
    return payload


def main() -> None:
    key = _load_key()
    OUT.mkdir(parents=True, exist_ok=True)
    inventory = []
    for sid, role in SERIES.items():
        raw = _fetch(sid, key)
        rows = []
        for obs in raw["observations"]:
            val = obs.get("value")
            if val in (None, ".", ""):
                continue
            try:
                num = float(val)
            except ValueError:
                continue
            rows.append({"date": obs["date"], "value": num})
        if not rows:
            raise SystemExit(f"FRED {sid}: zero numeric observations")
        csv_path = OUT / f"{sid}.csv"
        lines = ["date,value\n"]
        lines.extend(f"{r['date']},{r['value']}\n" for r in rows)
        csv_path.write_text("".join(lines))
        inventory.append(
            {
                "series_id": sid,
                "role": role,
                "n": len(rows),
                "min_date": rows[0]["date"],
                "max_date": rows[-1]["date"],
                "csv": str(csv_path.relative_to(_ROOT)),
            }
        )
        print(f"{sid:10} n={len(rows):5d}  {rows[0]['date']} → {rows[-1]['date']}")
    source = {
        "attribution": "Federal Reserve Bank of St. Louis / FRED",
        "url": "https://fred.stlouisfed.org/",
        "api": "https://api.stlouisfed.org/fred/series/observations",
        "auth": "env: FRED_API_KEY",
        "observation_start": START,
        "fetched_at": datetime.now(UTC).isoformat(),
        "use": "offline XAU research cache; not a republished FRED product",
        "series": inventory,
    }
    (OUT / "SOURCE.json").write_text(json.dumps(source, indent=2) + "\n")
    print(f"wrote {OUT / 'SOURCE.json'}")


if __name__ == "__main__":
    main()
