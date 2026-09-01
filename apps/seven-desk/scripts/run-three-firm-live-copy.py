#!/usr/bin/env python3
"""Min-lot live copy test: FTMO master, WSF + FundedNext slaves. Then close all.

Never touches ~/.mt5-vantage or ~/.mt5-fpmarkets. No passwords printed.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

HOME = Path.home()
REPO = Path("/home/yderf/Projects/trading/mt5-arch-integration")
SRC = REPO / "apps/seven-desk/mql5/DeskLiveOrder.mq5"
SCRIPT = "DeskLiveOrder"
FORBIDDEN = (".mt5-vantage", ".mt5-fpmarkets", ".mt5-exness")

FIRMS = {
    "ftmo": {
        "role": "master",
        "prefix": HOME / ".mt5-ftmo",
        "brands": ("FTMO Global Markets MT5 Terminal", "MetaTrader 5"),
        "login": "541163357",
        "confirm": "FTMO-541163357",
        "needle": "FTMO",
        "server": "FTMO-Server4",
        "magic": 20263848,
        "symbol": "EURUSD",
    },
    "wsf": {
        "role": "slave",
        "prefix": HOME / ".mt5-wsf",
        "brands": ("WSFmarkets MT5 Terminal", "MetaTrader 5"),
        "login": "149736",
        "confirm": "WSF-149736",
        "needle": "WSF",
        "server": "WSFmarkets-Server",
        "magic": 20263847,
        "symbol": "EURUSDc",
    },
    "fundednext": {
        "role": "slave",
        "prefix": HOME / ".mt5-fundednext",
        "brands": ("FundedNext MT5 Terminal", "MetaTrader 5"),
        "login": "13981906",
        "confirm": "FN-13981906",
        "needle": "FundedNext",
        "server": "FundedNext-Server 2",
        "magic": 20263849,
        "symbol": "EURUSD",
    },
}


def wine_env(prefix: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    env["WINEARCH"] = "win64"
    env["WINEDEBUG"] = "-all"
    env["DISPLAY"] = os.environ.get("DISPLAY") or ":0"
    env.pop("WAYLAND_DISPLAY", None)
    env.pop("LD_PRELOAD", None)
    env.setdefault("WINEDLLOVERRIDES", "d3d11=b;d3d12=b;dxgi=b")
    return env


def brand_dir(firm: dict) -> Path:
    prefix: Path = firm["prefix"]
    for brand in firm["brands"]:
        d = prefix / "drive_c/Program Files" / brand
        if (d / "terminal64.exe").is_file():
            return d
    raise SystemExit(f"no terminal64 under {prefix}")


def assert_allowed(prefix: Path) -> None:
    text = str(prefix.resolve())
    for marker in FORBIDDEN:
        if marker in text:
            raise SystemExit(f"refusing forbidden prefix {marker}")


def list_prefix_pids(prefix: Path) -> list[int]:
    want = str(prefix.resolve())
    pids: list[int] = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            cmd = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode()
        except OSError:
            continue
        if "terminal64.exe" not in cmd or "bash" in cmd:
            continue
        got = ""
        try:
            for part in (proc / "environ").read_bytes().split(b"\0"):
                if part.startswith(b"WINEPREFIX="):
                    got = os.path.realpath(part.split(b"=", 1)[1].decode())
                    break
        except OSError:
            continue
        if got == want:
            pids.append(int(proc.name))
    return pids


def start_background(firm: dict) -> None:
    prefix: Path = firm["prefix"]
    assert_allowed(prefix)
    if list_prefix_pids(prefix):
        print(f"  terminal already up {prefix.name}")
        return
    bdir = brand_dir(firm)
    log = Path(f"/tmp/mt5-{prefix.name}-terminal.log")
    args = ["wine", "./terminal64.exe", "/portable"]
    if (bdir / "auto_login.ini").is_file():
        args.append("/config:auto_login.ini")
    subprocess.Popen(
        args,
        cwd=bdir,
        env=wine_env(prefix),
        stdout=log.open("ab"),
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    print(f"  started {prefix.name} in background")
    try:
        sys.path.insert(0, str(REPO / "src"))
        from mt5_arch.hypr_geometry import park_prefix_terminals_silent

        ws = int(os.environ.get("MT5_BG_WORKSPACE", "11"))
        park_prefix_terminals_silent(str(prefix), ws)
    except Exception:
        pass


def stop_prefix(prefix: Path) -> list[int]:
    stopped = list_prefix_pids(prefix)
    for pid in stopped:
        with suppress(OSError):
            os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 5
    while time.time() < deadline and list_prefix_pids(prefix):
        time.sleep(0.2)
    for pid in list_prefix_pids(prefix):
        with suppress(OSError):
            os.kill(pid, signal.SIGKILL)
    return stopped


def compile_script(firm: dict) -> None:
    bdir = brand_dir(firm)
    scripts = bdir / "MQL5/Scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    dest = scripts / f"{SCRIPT}.mq5"
    dest.write_bytes(SRC.read_bytes())
    ex5 = scripts / f"{SCRIPT}.ex5"
    if ex5.exists() and ex5.stat().st_mtime >= dest.stat().st_mtime:
        return
    editor = bdir / "MetaEditor64.exe"
    if not editor.is_file():
        raise SystemExit(f"MetaEditor missing in {bdir}")
    subprocess.run(
        ["wine", str(editor), f"/compile:{SCRIPT}.mq5", "/log"],
        cwd=scripts,
        env=wine_env(firm["prefix"]),
        timeout=45,
        check=False,
    )
    if not ex5.is_file():
        raise SystemExit(f"compile failed for {firm['prefix'].name}")


def write_request(firm: dict, action: str, request_id: str) -> Path:
    bdir = brand_dir(firm)
    files = bdir / "MQL5/Files/mt5_arch"
    files.mkdir(parents=True, exist_ok=True)
    req = files / "desk_live_order_request.txt"
    res = files / "desk_live_order_result.json"
    if res.exists():
        res.unlink()
    req.write_text(
        "\n".join(
            [
                f"request_id={request_id}",
                f"action={action}",
                f"symbol={firm['symbol']}",
                "side=BUY",
                f"confirm={firm['confirm']}",
                f"expect_confirm={firm['confirm']}",
                f"expect_login={firm['login']}",
                f"expect_needle={firm['needle']}",
                "volume=0.01",
                "use_volume_min=1",
                f"magic={firm['magic']}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return files


def read_auto_login_password(bdir: Path) -> str:
    src = bdir / "auto_login.ini"
    if not src.is_file():
        return ""
    raw = src.read_bytes()
    text = raw.decode("utf-8", errors="replace").replace("\r", "")
    for line in text.splitlines():
        if line.startswith("Password="):
            return line.split("=", 1)[1]
    return ""


def write_ini(firm: dict) -> Path:
    bdir = brand_dir(firm)
    ini = bdir / "desk_live_order.ini"
    password = read_auto_login_password(bdir)
    common = [
        "[Common]",
        f"Login={firm['login']}",
        f"Server={firm['server']}",
        "ProxyEnable=0",
        "KeepPrivate=1",
        "NewsEnable=0",
        "CertInstall=1",
    ]
    if password:
        common.insert(3, f"Password={password}")
    text = (
        "\n".join(common)
        + "\n[Charts]\nMaxBars=100000\nPreloadCharts=1\n"
        "[Experts]\nAllowLiveTrading=1\nEnabled=1\nAccount=1\nProfile=1\n"
        "[StartUp]\n"
        f"Script={SCRIPT}\n"
        f"Symbol={firm['symbol']}\n"
        "Period=M1\n"
        "ShutdownTerminal=1\n"
    )
    ini.write_bytes(text.replace("\n", "\r\n").encode("ascii"))
    ini.chmod(0o600)
    return ini


def read_result(files: Path) -> dict:
    res = files / "desk_live_order_result.json"
    if not res.is_file():
        return {"ok": False, "reason": "no result json", "stage": "timeout"}
    raw = res.read_text(encoding="utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "reason": raw[:240], "stage": "parse"}


def wait_result(files: Path, timeout: float = 35) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = read_result(files)
        if result.get("stage") != "timeout":
            return result
        time.sleep(0.5)
    return read_result(files)


def run_action(name: str, firm: dict, action: str) -> dict:
    assert_allowed(firm["prefix"])
    compile_script(firm)
    request_id = f"{name}-{action}-{int(time.time())}"
    files = write_request(firm, action, request_id)
    ini = write_ini(firm)
    stopped = stop_prefix(firm["prefix"])
    bdir = brand_dir(firm)
    try:
        proc = subprocess.run(
            ["wine", "./terminal64.exe", "/portable", "/config:desk_live_order.ini"],
            cwd=bdir,
            env=wine_env(firm["prefix"]),
            timeout=90,
            check=False,
        )
        result = wait_result(files)
        result["wine_status"] = proc.returncode
    except subprocess.TimeoutExpired:
        result = wait_result(files, timeout=5)
        result["wine_status"] = "timeout"
    finally:
        if ini.exists():
            ini.unlink()
    result["firm"] = name
    result["role"] = firm["role"]
    result["action"] = action
    result["stopped"] = stopped
    start_background(firm)
    print(
        f"  {name} {action}: ok={result.get('ok')} login={result.get('login')} "
        f"order={result.get('order')} deal={result.get('deal_open') or result.get('deal_close')} "
        f"px={result.get('open_price') or result.get('close_price')} "
        f"reason={result.get('reason')}"
    )
    return result


def wait_snapshots(timeout: float = 40) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        ok = True
        for _name, firm in FIRMS.items():
            bdir = brand_dir(firm)
            acc = bdir / "MQL5/Files/mt5_arch/account.json"
            if not acc.is_file():
                ok = False
                continue
            try:
                data = json.loads(acc.read_text())
            except json.JSONDecodeError:
                ok = False
                continue
            if str(data.get("login")) != firm["login"]:
                ok = False
        if ok:
            print("snapshots ready")
            return
        time.sleep(2)
    print("warning: snapshots not all fresh; one-shot will re-login via /config")


def main() -> int:
    print("ensuring WSF / FTMO / FundedNext terminals (not Vantage/FP)")
    for firm in FIRMS.values():
        start_background(firm)
    time.sleep(4)
    wait_snapshots()

    print("MASTER open: FTMO")
    master = run_action("ftmo", FIRMS["ftmo"], "open")
    if not master.get("ok"):
        print("master open failed — not sending copies")
        return 1

    print("COPY open: WSF then FundedNext")
    copies = [
        run_action("wsf", FIRMS["wsf"], "open"),
        run_action("fundednext", FIRMS["fundednext"], "open"),
    ]
    print("CLOSE all (min-lot test, do not leave challenge positions)")
    closes = []
    for name in ("ftmo", "wsf", "fundednext"):
        result = run_action(name, FIRMS[name], "close")
        if not result.get("ok"):
            print(f"  retry close {name}")
            result = run_action(name, FIRMS[name], "close")
        closes.append(result)
    out = {"master": master, "copies": copies, "closes": closes}
    Path("/tmp/seven-desk-three-firm-live.json").write_text(json.dumps(out, indent=2))
    print("wrote /tmp/seven-desk-three-firm-live.json")
    failed = [row for row in [master, *copies, *closes] if not row.get("ok")]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
