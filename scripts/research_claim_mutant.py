#!/usr/bin/env python3
"""Mutant gate for research-claim-audit.

Seeds known-bad claims and routes them through scripts/research_claim_verify.py
(same resolve_one / predicates Verify uses). Also proves the gate can fail by
temporarily breaking the verifier.

Scratch-only: does not mutate worktree docs or tracked research state.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from copy import deepcopy
from pathlib import Path


def _load_verify(root: Path):
    path = root / "scripts" / "research_claim_verify.py"
    spec = importlib.util.spec_from_file_location("research_claim_verify", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def flip_hex_char(s: str) -> str:
    chars = list(s)
    for i in range(len(chars) - 1, -1, -1):
        c = chars[i].lower()
        if c in "0123456789abcdef":
            chars[i] = "0" if c != "0" else "1"
            return "".join(chars)
    raise RuntimeError(f"no hex digit to flip in {s!r}")


def flip_metric_digit(claimed: str) -> str:
    chars = list(claimed)
    for i in range(len(chars) - 1, -1, -1):
        if chars[i].isdigit():
            chars[i] = "9" if chars[i] != "9" else "8"
            return "".join(chars)
    raise RuntimeError(f"no digit to flip in {claimed!r}")


def invert_disposition(claimed: str) -> str:
    c = claimed.strip()
    if c.startswith("promote="):
        val = c.split("=", 1)[1].lower()
        return "promote=true" if val in {"no", "false"} else "promote=no"
    if c.startswith("live_go="):
        val = c.split("=", 1)[1].lower()
        return "live_go=true" if val in {"false", "no"} else "live_go=false"
    if c == "RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS":
        return "AWAIT_PHASE_E_SCREEN_AUTHORIZATION"
    raise RuntimeError(f"no invert rule for disposition {claimed!r}")


def _act_is_results_oracle(act: str) -> bool:
    return isinstance(act, str) and "results/" in act


def _pick_anchors(v, claims: list[dict], tracked: set[str]) -> dict[str, dict]:
    """Pick currently-ok anchors so mutants exercise real checkers."""
    wanted: dict[str, dict | None] = {
        "path": None,
        "sha": None,
        "metric": None,
        "metric_md": None,
        "disposition": None,
    }
    preferred = [
        (
            "path",
            lambda c: c["kind"] == "path"
            and c["claimed"] == "scripts/16-use-broker.sh"
            and str(c["file"]).endswith("README.md"),
        ),
        (
            "sha",
            lambda c: c["kind"] == "sha"
            and c["claimed"].startswith("11099b2a")
            and "early_server" in (c.get("attribution") or ""),
        ),
        (
            "metric",
            # Restating doc (NOT BACKTEST-RECORD) so a results oracle survives.
            lambda c: c["kind"] == "metric"
            and "PF" in c["claimed"]
            and not str(c["file"]).endswith("BACKTEST-RECORD.md")
            and not str(c["file"]).startswith("results/")
            and (
                "HOWTO-US-INDEX" in str(c["file"])
                or "SIGNAL-EDGE" in str(c["file"])
            ),
        ),
        (
            "metric_md",
            # Metric backed by a named/results/*.md write-up (exercises md oracle path).
            lambda c: c["kind"] == "metric"
            and c["claimed"].startswith("PF ")
            and re.search(r"PF\s+\d+\.\d+", c["claimed"])
            and "US-INDEX-SESSION-SCALP-DESIGN" in str(c["file"])
            and c.get("line") == 92,
        ),
        (
            "disposition",
            lambda c: c["kind"] == "disposition"
            and c["claimed"] in ("promote=no", "promote=false"),
        ),
    ]
    for kind, pred in preferred:
        for c in claims:
            if pred(c):
                st, act = v.resolve_one(c, tracked)
                if st != "ok":
                    continue
                if kind in ("metric", "metric_md") and not _act_is_results_oracle(str(act)):
                    continue
                # metric_md must specifically hit a .md write-up
                if kind == "metric_md" and ".md" not in str(act):
                    continue
                wanted[kind] = c
                break

    for c in claims:
        kind = c["kind"]
        keys: list[str] = []
        if kind in ("path", "sha", "disposition") and wanted.get(kind) is None:
            keys.append(kind)
        if kind == "metric":
            if wanted["metric"] is None:
                keys.append("metric")
            if wanted["metric_md"] is None and "US-INDEX" in str(c["file"]):
                keys.append("metric_md")
        for key in keys:
            if key in ("metric", "metric_md") and (
                str(c["file"]).endswith("BACKTEST-RECORD.md")
                or str(c["file"]).startswith("results/")
            ):
                continue
            st, act = v.resolve_one(c, tracked)
            if st != "ok":
                continue
            if key in ("metric", "metric_md") and not _act_is_results_oracle(str(act)):
                continue
            if key == "metric_md" and ".md" not in str(act):
                continue
            wanted[key] = c
            break

    missing = [k for k, c in wanted.items() if c is None]
    if missing:
        raise RuntimeError(
            "FAIL LOUDLY: cannot seed mutants — anchors missing/moved for "
            + ",".join(missing)
            + ". Re-extract inventory or restore ok anchors."
        )
    return wanted  # type: ignore[return-value]


def _seed_mutants(anchors: dict[str, dict]) -> list[dict]:
    seeds = []
    path_c = deepcopy(anchors["path"])
    path_c["claimed"] = "scripts/__mutant_dead_path_does_not_exist__.sh"
    seeds.append({"seed_kind": "dead_path", "orig": anchors["path"], "mutant": path_c})

    sha_c = deepcopy(anchors["sha"])
    sha_c["claimed"] = flip_hex_char(sha_c["claimed"])
    seeds.append({"seed_kind": "sha_one_char", "orig": anchors["sha"], "mutant": sha_c})

    met_c = deepcopy(anchors["metric"])
    met_c["claimed"] = flip_metric_digit(met_c["claimed"])
    seeds.append({"seed_kind": "metric_digit", "orig": anchors["metric"], "mutant": met_c})

    met_md = deepcopy(anchors["metric_md"])
    met_md["claimed"] = flip_metric_digit(met_md["claimed"])
    seeds.append(
        {
            "seed_kind": "metric_md_writeup",
            "orig": anchors["metric_md"],
            "mutant": met_md,
        }
    )

    disp_c = deepcopy(anchors["disposition"])
    disp_c["claimed"] = invert_disposition(disp_c["claimed"])
    seeds.append(
        {"seed_kind": "inverted_disposition", "orig": anchors["disposition"], "mutant": disp_c}
    )
    return seeds


def _eval_seeds(v, seeds: list[dict], tracked: set[str]) -> tuple[list[dict], int]:
    per = []
    n_caught = 0
    for s in seeds:
        status, actual = v.resolve_one(s["mutant"], tracked)
        # Caught only means reported as drift. unresolvable is NOT caught —
        # that is the verifier saying "I cannot tell", which the gate must detect.
        caught = status == "drift"
        if caught:
            n_caught += 1
        per.append(
            {
                "seed_kind": s["seed_kind"],
                "kind": s["mutant"]["kind"],
                "file": s["mutant"].get("file"),
                "line": s["mutant"].get("line"),
                "orig_claimed": s["orig"]["claimed"],
                "mutant_claimed": s["mutant"]["claimed"],
                "attribution": s["mutant"].get("attribution"),
                "status": status,
                "actual": actual,
                "caught": caught,
            }
        )
    return per, n_caught


def run_gate(root: Path | None = None) -> dict:
    root = root or Path.cwd()
    v = _load_verify(root)
    inv_path = v.INV
    if not inv_path.is_file():
        return {
            "ok": False,
            "mutant_caught": False,
            "gate_can_fail": False,
            "n_seeded": 0,
            "n_caught": 0,
            "evidence": f"FAIL LOUDLY: inventory missing at {inv_path}",
        }

    data = json.loads(inv_path.read_text())
    claims = data["claims"]
    tracked = v.run_git_ls_files()

    try:
        anchors = _pick_anchors(v, claims, tracked)
        seeds = _seed_mutants(anchors)
    except RuntimeError as e:
        return {
            "ok": False,
            "mutant_caught": False,
            "gate_can_fail": False,
            "n_seeded": 0,
            "n_caught": 0,
            "evidence": str(e),
        }

    # --- Prove the gate can fail: break verifier to always-ok, expect 0 caught ---
    real_resolve = v.resolve_one

    def broken_resolve(claim, tracked=None):  # noqa: ANN001
        return "ok", "broken_verifier_always_ok"

    v.resolve_one = broken_resolve  # type: ignore[method-assign]
    broken_per, broken_caught = _eval_seeds(v, seeds, tracked)
    v.resolve_one = real_resolve  # type: ignore[method-assign]
    gate_can_fail = broken_caught == 0
    if not gate_can_fail:
        return {
            "ok": False,
            "mutant_caught": False,
            "gate_can_fail": False,
            "n_seeded": len(seeds),
            "n_caught": broken_caught,
            "evidence": (
                "FAIL LOUDLY: broken verifier still caught mutants — gate is not "
                f"routing through resolve_one (broken_caught={broken_caught})"
            ),
            "broken_per_seed": broken_per,
        }

    # --- Real mutant run through the live verifier ---
    per, n_caught = _eval_seeds(v, seeds, tracked)
    mutant_caught = n_caught == len(seeds)
    evidence = " | ".join(
        f"{p['seed_kind']}: orig={p['orig_claimed']!r}->{p['mutant_claimed']!r} "
        f"status={p['status']} caught={p['caught']}"
        for p in per
    )
    evidence = (
        f"gate_can_fail={gate_can_fail} (broken verifier caught {broken_caught}/"
        f"{len(seeds)}); " + evidence
    )
    return {
        "ok": mutant_caught and gate_can_fail,
        "mutant_caught": mutant_caught,
        "gate_can_fail": gate_can_fail,
        "n_seeded": len(seeds),
        "n_caught": n_caught,
        "evidence": evidence,
        "per_seed": per,
        "broken_caught": broken_caught,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--out",
        type=Path,
        default=Path("results/research_claim_mutant_result.json"),
        help="result JSON (repo-relative default)",
    )
    args = p.parse_args(argv)

    # Ensure ROOT aligns with verifier
    vprobe = _load_verify(Path.cwd())
    root = vprobe.ROOT
    out = args.out if args.out.is_absolute() else root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)

    result = run_gate(root)
    out.write_text(json.dumps(result, indent=2) + "\n")
    try:
        out_disp = str(out.resolve().relative_to(root.resolve()))
    except ValueError:
        out_disp = str(out.resolve())
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "mutant_caught": result["mutant_caught"],
                "gate_can_fail": result["gate_can_fail"],
                "n_seeded": result["n_seeded"],
                "n_caught": result["n_caught"],
                "out": out_disp,
            },
            indent=2,
        )
    )
    print(result.get("evidence", ""))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
