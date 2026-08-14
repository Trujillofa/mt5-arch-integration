"""Article-intake gate: catalog PF is not evidence; holdout never selects."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from verify_article_intake import (  # noqa: E402
    INTAKE_SCHEMA,
    ArticleIntakeError,
    verify_intake,
)

VERIFY = ROOT / "scripts" / "verify_article_intake.py"
EXAMPLE = ROOT / "docs" / "intake" / "article_intake.example.json"
VALID = ROOT / "tests" / "fixtures" / "article_intake" / "valid.json"
PLATFORM_SRC = ROOT / "src" / "mt5_arch"


def _write(tmp_path: Path, raw: dict) -> Path:
    dest = tmp_path / "article_intake.json"
    dest.write_text(json.dumps(raw), encoding="utf-8")
    return dest


def test_valid_reject_fixture():
    report = verify_intake(VALID, repo_root=ROOT)
    assert report["ok"] is True
    assert report["schema"] == INTAKE_SCHEMA
    assert report["decision"] == "reject"
    assert report["claim_type"] == "pf"
    assert report["independent_python"] is False
    assert report["holdout_used_for_selection"] is False


def test_docs_example_matches_valid_fixture():
    assert EXAMPLE.read_text(encoding="utf-8") == VALID.read_text(encoding="utf-8")
    report = verify_intake(EXAMPLE, repo_root=ROOT)
    assert report["ok"] is True
    assert report["decision"] == "reject"


def test_adopt_with_independent_python(tmp_path: Path):
    raw = json.loads(VALID.read_text(encoding="utf-8"))
    raw["claim_type"] = "math"
    raw["independent_python"] = "scripts/htf_fib_core.py"
    raw["parity_package"] = "htf_fib"
    raw["decision"] = "adopt"
    raw["reason"] = (
        "Independent confirm-bar Wilder ATR already exists in htf_fib_core; "
        "catalog PF was not used for selection."
    )
    report = verify_intake(_write(tmp_path, raw), repo_root=ROOT)
    assert report["ok"] is True
    assert report["decision"] == "adopt"
    assert report["independent_python"] == "scripts/htf_fib_core.py"


@pytest.mark.parametrize("field", [
    "schema",
    "article_url",
    "claim_type",
    "independent_python",
    "parity_package",
    "holdout_used_for_selection",
    "decision",
    "reason",
])
def test_missing_field_refuses(tmp_path: Path, field: str):
    raw = json.loads(VALID.read_text(encoding="utf-8"))
    del raw[field]
    with pytest.raises(ArticleIntakeError, match="missing field"):
        verify_intake(_write(tmp_path, raw), repo_root=ROOT)


def test_holdout_used_for_selection_refuses(tmp_path: Path):
    raw = json.loads(VALID.read_text(encoding="utf-8"))
    raw["holdout_used_for_selection"] = True
    with pytest.raises(ArticleIntakeError, match="holdout_used_for_selection"):
        verify_intake(_write(tmp_path, raw), repo_root=ROOT)


def test_holdout_string_false_refuses(tmp_path: Path):
    raw = json.loads(VALID.read_text(encoding="utf-8"))
    raw["holdout_used_for_selection"] = "false"
    with pytest.raises(ArticleIntakeError, match="holdout_used_for_selection"):
        verify_intake(_write(tmp_path, raw), repo_root=ROOT)


def test_adopt_without_independent_python_refuses(tmp_path: Path):
    raw = json.loads(VALID.read_text(encoding="utf-8"))
    raw["decision"] = "adopt"
    raw["independent_python"] = False
    raw["reason"] = "Catalog PF looked good."
    with pytest.raises(ArticleIntakeError, match="decision=adopt requires independent_python"):
        verify_intake(_write(tmp_path, raw), repo_root=ROOT)


def test_adopt_with_missing_python_file_refuses(tmp_path: Path):
    raw = json.loads(VALID.read_text(encoding="utf-8"))
    raw["decision"] = "adopt"
    raw["independent_python"] = "scripts/does_not_exist_catalog_port.py"
    with pytest.raises(ArticleIntakeError, match="does not exist"):
        verify_intake(_write(tmp_path, raw), repo_root=ROOT)


def test_secret_key_refuses(tmp_path: Path):
    raw = json.loads(VALID.read_text(encoding="utf-8"))
    raw["password"] = "nope"
    with pytest.raises(ArticleIntakeError, match="secret key"):
        verify_intake(_write(tmp_path, raw), repo_root=ROOT)


def test_nested_api_key_refuses(tmp_path: Path):
    raw = json.loads(VALID.read_text(encoding="utf-8"))
    raw["meta"] = {"api_key": "nope"}
    with pytest.raises(ArticleIntakeError, match="secret key"):
        verify_intake(_write(tmp_path, raw), repo_root=ROOT)


def test_catalog_mq5_without_python_refuses(tmp_path: Path):
    raw = json.loads(VALID.read_text(encoding="utf-8"))
    raw["catalog_mq5"] = "mql5/Experts/CatalogCopy.mq5"
    with pytest.raises(ArticleIntakeError, match="catalog .mq5 without independent python"):
        verify_intake(_write(tmp_path, raw), repo_root=ROOT)


def test_independent_python_mq5_refuses(tmp_path: Path):
    raw = json.loads(VALID.read_text(encoding="utf-8"))
    raw["decision"] = "adopt"
    raw["independent_python"] = "mql5/Experts/CatalogCopy.mq5"
    with pytest.raises(ArticleIntakeError, match=r"not catalog \.mq5|\.py"):
        verify_intake(_write(tmp_path, raw), repo_root=ROOT)


def test_catalog_mq5_with_python_path_passes(tmp_path: Path):
    raw = json.loads(VALID.read_text(encoding="utf-8"))
    raw["claim_type"] = "pattern"
    raw["catalog_mq5"] = "docs/intake/not-imported-example.mq5"
    raw["independent_python"] = "scripts/htf_fib_core.py"
    raw["parity_package"] = "htf_fib"
    raw["decision"] = "defer"
    raw["reason"] = "Noted catalog filename only; independent Python already exists; holdout sealed."
    report = verify_intake(_write(tmp_path, raw), repo_root=ROOT)
    assert report["ok"] is True
    assert report["decision"] == "defer"


@pytest.mark.parametrize(
    ("field", "value", "needle"),
    [
        ("claim_type", "edge", "claim_type"),
        ("parity_package", "catalog", "parity_package"),
        ("decision", "promote", "decision"),
        ("article_url", "mql5.com/en/code/1", "article_url"),
        ("reason", "   ", "reason"),
        ("schema", "mt5-article-intake/v0", "schema"),
    ],
)
def test_invalid_enum_or_empty_refuses(tmp_path: Path, field: str, value: object, needle: str):
    raw = json.loads(VALID.read_text(encoding="utf-8"))
    raw[field] = value
    with pytest.raises(ArticleIntakeError, match=needle):
        verify_intake(_write(tmp_path, raw), repo_root=ROOT)


def test_committed_fixture_has_no_secrets():
    text = VALID.read_text(encoding="utf-8").lower()
    assert "password" not in text
    assert "mt5_password" not in text
    assert "api_key" not in text
    assert ".mq5" not in text


def test_verifier_stays_out_of_platform_package():
    imports = [
        line
        for line in VERIFY.read_text(encoding="utf-8").splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]
    joined = "\n".join(imports)
    assert "mt5_arch" not in joined
    assert "xau_" not in joined
    assert "backtest" not in joined
    assert not (PLATFORM_SRC / "article_intake.py").exists()


def test_tests_and_verifier_never_place_orders():
    text = VERIFY.read_text(encoding="utf-8")
    assert "OrderSend" not in text
    assert "order_send" not in text


def test_verify_cli_default_fixture():
    proc = subprocess.run(
        ["python3", str(VERIFY)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "PASSED" in proc.stdout


def test_verify_cli_example_json():
    proc = subprocess.run(
        ["python3", str(VERIFY), str(EXAMPLE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "PASSED" in proc.stdout
