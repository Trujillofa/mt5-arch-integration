#!/usr/bin/env python3
"""Re-derive results/research_claim_selfref_allow.json (stdlib-only).

After a scope change, self-referential metric claims must be re-searched against
tracked results/** — never hand-edited. For each verify status==self_referential
row, record n_searched + searched_sample + reason from the attribution-gated
full-tree search already performed by resolve_metric.

  python3 scripts/research_claim_selfref_rebuild.py
  python3 scripts/research_claim_selfref_rebuild.py --out PATH
  python3 scripts/research_claim_selfref_rebuild.py --dry-run
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


def _load_verify_mod():
    import importlib.util

    mod_path = Path(__file__).resolve().parent / "research_claim_verify.py"
    spec = importlib.util.spec_from_file_location("research_claim_verify", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _parse_searched_note(actual: str) -> tuple[int, list[str]]:
    """Parse n_searched + sample list from resolve_metric's claiming_file_only note."""
    text = actual or ""
    m = re.search(r"n_searched=(\d+)", text)
    n = int(m.group(1)) if m else 0
    sample: list[str] = []
    sm = re.search(r"sample=(\[[^\]]*\])", text)
    if sm:
        try:
            parsed = ast.literal_eval(sm.group(1))
            if isinstance(parsed, list):
                sample = [str(x) for x in parsed]
        except (SyntaxError, ValueError):
            sample = []
    return n, sample


def _reason_for(row: dict[str, Any], n_searched: int) -> str:
    src = str(row.get("file") or "")
    claimed = str(row.get("claimed") or "")
    if "SIGNAL-EDGE-TRIAGE" in src:
        return (
            f"Lane-all / triage table figure {claimed!r} originates in docs/ "
            f"(tool writes nothing). Full-tree attribution-gated search "
            f"n_searched={n_searched}."
        )
    if src.endswith("BACKTEST-RECORD.md"):
        return (
            f"SoT ledger prose figure {claimed!r}; no structured results/** "
            f"oracle matched. Full-tree attribution-gated search "
            f"n_searched={n_searched}."
        )
    if "US-INDEX-SESSION" in src or "HOWTO-US-INDEX" in src:
        return (
            f"Design/HOWTO narrative metric {claimed!r}; named/tied results/** "
            f"miss after full-tree attribution-gated search n_searched={n_searched}."
        )
    return (
        f"Claiming-file-only metric {claimed!r} after attribution-gated full-tree "
        f"results/** search (n_searched={n_searched}); no oracle match outside the "
        f"claiming doc."
    )


def build_allowlist(root: Path | None = None) -> dict[str, Any]:
    v = _load_verify_mod()
    root = root or Path(v.ROOT)
    inv_path = root / "results" / "research_claim_inventory.json"
    data = json.loads(inv_path.read_text())
    claims = list(data.get("claims") or [])
    tracked = v.run_git_ls_files()
    report = v.verify_claims(claims, tracked=tracked)
    n_results = len(v._tracked_results_files(tracked))

    allow: list[dict[str, Any]] = []
    skipped_zero: list[dict[str, Any]] = []
    for row in report.get("self_referential") or []:
        n_searched, sample = _parse_searched_note(str(row.get("actual") or ""))
        if n_searched <= 0:
            skipped_zero.append(
                {
                    "file": row.get("file"),
                    "line": row.get("line"),
                    "kind": row.get("kind"),
                    "claimed": row.get("claimed"),
                    "actual": row.get("actual"),
                }
            )
            continue
        allow.append(
            {
                "file": row.get("file"),
                "line": row.get("line"),
                "kind": row.get("kind"),
                "claimed": row.get("claimed"),
                "n_searched": n_searched,
                "searched_sample": sample[:5],
                "reason": _reason_for(row, n_searched),
            }
        )

    allow.sort(key=lambda r: (r["file"] or "", int(r["line"] or 0), r["kind"] or "", r["claimed"] or ""))
    return {
        "schema": "research_claim_selfref_allow_v1",
        "note": (
            "Regenerated after full tracked results/** search. Each entry carries "
            "n_searched from attribution-gated full-tree search. Reasons must not "
            "assert missing artifacts on a partial search. Built by "
            "scripts/research_claim_selfref_rebuild.py — do not hand-edit."
        ),
        "search_scope": "git ls-files results/** (excluding csv/instrument_data/research_claim_*)",
        "n_results_tracked": n_results,
        "n_self_referential": int(report.get("n_self_referential") or 0),
        "n_allow": len(allow),
        "n_skipped_n_searched_zero": len(skipped_zero),
        "skipped_n_searched_zero": skipped_zero,
        "allow": allow,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--out",
        type=Path,
        default=Path("results/research_claim_selfref_allow.json"),
        help="allowlist JSON path",
    )
    p.add_argument("--dry-run", action="store_true", help="print summary; do not write")
    args = p.parse_args(argv)

    payload = build_allowlist()
    summary = {
        "ok": payload["n_skipped_n_searched_zero"] == 0,
        "n_self_referential": payload["n_self_referential"],
        "n_allow": payload["n_allow"],
        "n_skipped_n_searched_zero": payload["n_skipped_n_searched_zero"],
        "n_results_tracked": payload["n_results_tracked"],
    }
    print(json.dumps(summary, indent=2))
    if payload["skipped_n_searched_zero"]:
        print("---SKIPPED_N_SEARCHED_ZERO---")
        for s in payload["skipped_n_searched_zero"]:
            print(
                f"{s['file']}|{s['line']}|{s['kind']}|{s['claimed']}|{s.get('actual', '')}"
            )
    if args.dry_run:
        return 0 if summary["ok"] else 1

    out = args.out
    if not out.is_absolute():
        out = Path.cwd() / out
    # Persist allow file without the skipped diagnostic list (keep allow schema lean).
    written = {
        "schema": payload["schema"],
        "note": payload["note"],
        "search_scope": payload["search_scope"],
        "n_results_tracked": payload["n_results_tracked"],
        "allow": payload["allow"],
    }
    out.write_text(json.dumps(written, indent=2) + "\n")
    print(f"wrote {out}")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
