#!/usr/bin/env bash
# Force MT5 trade-server login from .env and re-attach the file-bridge EA.
# Uses MetaTrader /config: auto-login (does NOT print the password).
#
# Usage:
#   ./scripts/13-force-login-bridge.sh
#   ./scripts/13-force-login-bridge.sh --no-restart   # only write config + EA files
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env
require_cmd wine

NO_RESTART=0
for arg in "$@"; do
  case "$arg" in
    --no-restart) NO_RESTART=1 ;;
    -h|--help)
      echo "Usage: $0 [--no-restart]"
      exit 0
      ;;
  esac
done

[[ -n "${MT5_LOGIN:-}" ]] || die "MT5_LOGIN not set in .env"
[[ -n "${MT5_PASSWORD:-}" ]] || die "MT5_PASSWORD not set in .env"
[[ -n "${MT5_SERVER:-}" ]] || die "MT5_SERVER not set in .env"
case "${MT5_PASSWORD}" in
  your_mt5_password_here|changeme|password|secret)
    die "MT5_PASSWORD is still a placeholder — set the real master password (see config/brokers/)"
    ;;
esac

MT5_DIR="$WINEPREFIX/drive_c/Program Files/MetaTrader 5"
term="$(find_terminal64)" || die "terminal64.exe not found under WINEPREFIX=$WINEPREFIX"
# Guard against config/local.paths (or stale MT5_TERMINAL_PATH) pointing at another prefix
case "$term" in
  "$WINEPREFIX"/*) ;;
  *)
    die "terminal64 resolved outside WINEPREFIX ($term). Unset MT5_TERMINAL_PATH or fix config/local.paths. WINEPREFIX=$WINEPREFIX"
    ;;
esac
info "Using terminal: $term (WINEPREFIX=$WINEPREFIX)"
CONFIG_DIR="$MT5_DIR/Config"
# Place next to terminal64.exe so /config:auto_login.ini works without spaces/quoting issues
AUTO_INI="$MT5_DIR/auto_login.ini"
EXPERTS="$MT5_DIR/MQL5/Experts"
CHARTS="$MT5_DIR/MQL5/Profiles/Charts/Default"
LOG="$MT5_DIR/logs/$(date +%Y%m%d).log"
export AUTO_INI MT5_DIR EXPERTS CHARTS

mkdir -p "$CONFIG_DIR" "$EXPERTS" "$CHARTS"

# Prefer LAN for Wine when multiple NICs exist (Docker bridges confuse some builds)
if [[ -n "${DISPLAY:-}" ]]; then
  unset WAYLAND_DISPLAY || true
fi
export DISPLAY="${DISPLAY:-:0}"
export WINEDEBUG="${WINEDEBUG:--all}"
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-d3d11=b;d3d12=b;dxgi=b}"
# Prefer physical host address for multi-homed systems
if ip -4 -o addr show scope global 2>/dev/null | rg -q 'enp|eth|wlan'; then
  export WINE_PREFERRED_ROUTE_IFACE="$(ip -4 route show default 2>/dev/null | awk '{print $5; exit}')"
fi

# Prefer IPv4: Wine IPv6 connect often fails with STATUS_HOST_UNREACHABLE and
# can block trade-server login (no Network journal lines).
wine reg add 'HKLM\System\CurrentControlSet\Services\Tcpip6\Parameters' \
  /v DisabledComponents /t REG_DWORD /d 255 /f >/dev/null 2>&1 || true

# Optional: force LAN source IP so Wine does not bind Docker bridge addresses
# (see scripts/wine-net/force_src_bind.c). Safe no-op if .so missing.
FORCE_SO="$REPO_ROOT/scripts/wine-net/force_src_bind.so"
if [[ -f "$FORCE_SO" ]]; then
  LAN_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}' || true)"
  LAN_IP="${LAN_IP:-192.168.0.144}"
  export MT5_FORCE_SRC_IP="$LAN_IP"
  export LD_PRELOAD="$FORCE_SO${LD_PRELOAD:+:$LD_PRELOAD}"
  info "LAN source bind preload enabled (MT5_FORCE_SRC_IP=$LAN_IP)"
fi

info "Writing auto_login.ini for login=$MT5_LOGIN server=$MT5_SERVER (password not logged)"
# MetaTrader start config: ANSI/UTF-8 CRLF (UTF-16 rejected with "cannot load config").
# https://www.metatrader5.com/en/terminal/help/start_advanced/start
python3 - <<'PY'
from pathlib import Path
import os
login = os.environ["MT5_LOGIN"]
password = os.environ["MT5_PASSWORD"]
server = os.environ["MT5_SERVER"]
text = f"""[Common]
Login={login}
Password={password}
Server={server}
ProxyEnable=0
KeepPrivate=1
NewsEnable=1
CertInstall=1

[Experts]
AllowLiveTrading=1
Enabled=1
AllowDllImport=1
EnabledWebTrading=1

[Charts]
ProfileLast=Default
MaxBars=100000
PreloadCharts=1
"""
text = text.replace("\r\n", "\n").replace("\n", "\r\n")
path = Path(os.environ["AUTO_INI"])
path.write_bytes(text.encode("ascii", errors="strict"))
path.chmod(0o600)
print(f"wrote {path} ({path.stat().st_size} bytes) ascii/crlf")
PY

# Restore/ensure common.ini Experts flags (UTF-16)
python3 - <<'PY'
from pathlib import Path
import os
p = Path(os.environ["WINEPREFIX"]) / "drive_c/Program Files/MetaTrader 5/Config/common.ini"
env = "F008C7293503CED0045B07842FC57A638AA2FD5F10DEE8EA7AD19815A339B9A21E36157778467577E33A229F2FC5240D"
# Preserve Environment hash if present
if p.exists():
    raw = p.read_bytes()
    if raw[:2] == b"\xff\xfe":
        old = raw[2:].decode("utf-16-le", "replace")
        for line in old.splitlines():
            if line.startswith("Environment="):
                env = line.split("=", 1)[1].strip()
                break
text = f"""[Common]
Environment={env}
Login=0
Server=
ProxyEnable=0
ProxyType=0
ProxyAddress=
ProxyPort=0
ProxyLogin=
CertInstall=1
NewsEnable=1
Services=1
[Charts]
ProfileLast=Default
MaxBars=100000
PrintColor=0
SaveDeleted=0
TradeHistory=1
TradeLevels=1
TradeLevelsDrag=0
PreloadCharts=1
[Experts]
AllowLiveTrading=1
Enabled=1
Account=0
Profile=0
Chart=0
Api=0
DisableOpenCL=
AllowDllImport=1
EnabledWebTrading=1
[Notification]
Enable=0
Trade=0
TradeMarginCall=0
[Email]
Enable=0
[Events]
Enable=1
News=news.wav
NewsEnable=0
Expert Advisor=expert.wav
Expert AdvisorEnable=1
Alert=alert.wav
AlertEnable=1
"""
text = text.replace("\r\n", "\n").replace("\n", "\r\n")
p.write_bytes(b"\xff\xfe" + text.encode("utf-16-le"))
print(f"common.ini ok ({p.stat().st_size} bytes)")
PY

# Deploy EA source + attach to Default chart profile
info "Installing file-bridge EA on Default chart profile"
"$SCRIPT_DIR/06-install-file-bridge.sh" || warn "EA compile script warned; continuing if .ex5 exists"
[[ -f "$EXPERTS/Mt5ArchBridge.ex5" ]] || die "Mt5ArchBridge.ex5 missing after install"

python3 - <<'PY'
from pathlib import Path
good = Path.home() / ".mt5/drive_c/Program Files/MetaTrader 5/Profiles/Charts/Default/chart03.chr"
base = Path.home() / ".mt5/drive_c/Program Files/MetaTrader 5/MQL5/Profiles/Charts/Default"
base.mkdir(parents=True, exist_ok=True)
if good.exists() and good.read_bytes()[:2] == b"\xff\xfe":
    raw = good.read_bytes()
    if "Mt5ArchBridge" not in raw[2:].decode("utf-16-le", "replace"):
        # inject expert block before </chart>
        t = raw[2:].decode("utf-16-le")
        expert = (
            "\r\n<expert>\r\n"
            "name=Mt5ArchBridge\r\n"
            "path=Experts\\Mt5ArchBridge.ex5\r\n"
            "expertmode=5\r\n"
            "<inputs>\r\n"
            "InpTimerSec=1\r\n"
            "InpSymbols=EURUSD,GBPUSD,USDJPY,XAUUSD,USDCHF\r\n"
            "InpTimeframes=M15,H1,H4,D1\r\n"
            "InpCandleCount=50\r\n"
            "</inputs>\r\n"
            "</expert>\r\n"
        )
        if "Mt5ArchBridge" not in t:
            t = t.replace("</chart>", expert + "</chart>")
        raw = b"\xff\xfe" + t.encode("utf-16-le")
else:
    # Minimal GBPUSD H1 chart with EA (UTF-16 LE)
    body = """<chart>
id=1
symbol=GBPUSD
description=Pound vs US Dollar
period_type=1
period_size=1
digits=5
scale_fixed=0
scale=16
mode=1
fore=0
grid=1
volume=0
scroll=1
shift=0
fixed_pos=0.000000
ticker=1
ohlc=1
one_click=0
bidline=1
askline=0
lastline=0
days=0
descriptions=0
tradelines=1
tradehistory=1
window_left=0
window_top=0
window_right=800
window_bottom=500
window_type=1
floating=0
background_color=0
foreground_color=16777215
barup_color=65280
bardown_color=65280
bullcandle_color=0
bearcandle_color=16777215
chartline_color=65280
volumes_color=3329330
grid_color=10061943
bidline_color=10061943
askline_color=255
lastline_color=49152
stops_color=255
windows_total=1

<window>
height=100.000000
objects=0

<indicator>
name=Main
path=
apply=1
show_data=1
scale_inherit=0
scale_line=0
scale_line_percent=50
scale_line_value=0.000000
scale_fix_min=0
scale_fix_min_val=0.000000
scale_fix_max=0
scale_fix_max_val=0.000000
expertmode=0
fixed_height=-1
</indicator>
</window>

<expert>
name=Mt5ArchBridge
path=Experts\\Mt5ArchBridge.ex5
expertmode=5
<inputs>
InpTimerSec=1
InpSymbols=EURUSD,GBPUSD,USDJPY,XAUUSD,USDCHF
InpTimeframes=M15,H1,H4,D1
InpCandleCount=50
</inputs>
</expert>
</chart>
"""
    body = body.replace("\r\n", "\n").replace("\n", "\r\n")
    raw = b"\xff\xfe" + body.encode("utf-16-le")

for name in ("chart01.chr", "chart02.chr"):
    (base / name).write_bytes(raw)
    print("chart", name, "EA=yes")
PY

if [[ "$NO_RESTART" -eq 1 ]]; then
  info "Config + EA deployed (--no-restart). Start terminal with:"
  echo "  wine \"$term\" /portable /config:\"C:\\\\Program Files\\\\MetaTrader 5\\\\Config\\\\auto_login.ini\""
  exit 0
fi

info "Stopping MetaTrader / MetaEditor / wineserver processes"
# Kill wineserver too so LD_PRELOAD (force_src_bind) applies to a fresh server.
# A long-lived wineserver started without preload keeps Docker-bridge source IPs.
python3 - <<'PY'
import os, signal, time
keys = ("terminal64.exe", "MetaEditor64.exe", "metaeditor64.exe", "metatester64.exe", "wineserver")
for pid in list(os.listdir("/proc")):
    if not pid.isdigit():
        continue
    try:
        cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\x00", b" ").decode("utf-8", "replace")
    except OSError:
        continue
    if any(x in cmd for x in ("bash", "extglob", "python", "grok")):
        continue
    if any(k in cmd for k in keys):
        print(f"  stop {pid}")
        try:
            os.kill(int(pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
time.sleep(2)
for pid in list(os.listdir("/proc")):
    if not pid.isdigit():
        continue
    try:
        cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\x00", b" ").decode("utf-8", "replace")
    except OSError:
        continue
    if any(x in cmd for x in ("bash", "extglob", "python", "grok")):
        continue
    if any(k in cmd for k in keys):
        try:
            os.kill(int(pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
print("  done")
PY

# Fresh log for this attempt
LOG_DIR="$MT5_DIR/logs"
mkdir -p "$LOG_DIR"
TODAY="$(date +%Y%m%d)"
if [[ -f "$LOG_DIR/$TODAY.log" ]]; then
  mv -f "$LOG_DIR/$TODAY.log" "$LOG_DIR/${TODAY}.log.pre-force-login.$$" || true
fi

ensure_clipboard_bridge

info "Starting terminal with forced login config"
# Relative /config from terminal dir avoids Wine path/quoting bugs (saw: cannot load ...ini"")
(
  cd "$MT5_DIR"
  nohup wine "$term" /portable /config:auto_login.ini >>/tmp/mt5-force-login.log 2>&1 &
  echo $! > /tmp/mt5-force-login.pid
)
TPID="$(cat /tmp/mt5-force-login.pid)"
info "PID $TPID  log=/tmp/mt5-force-login.log  journal=$LOG_DIR/$TODAY.log"

info "Waiting up to 90s for Network auth or fresh account money fields..."
python3 - <<'PY'
import json, os, time
from pathlib import Path

prefix = Path(os.environ["WINEPREFIX"])
log = prefix / "drive_c/Program Files/MetaTrader 5/logs" / f"{time.strftime('%Y%m%d')}.log"
bridge = prefix / "drive_c/Program Files/MetaTrader 5/MQL5/Files/mt5_arch/account.json"
want_login = int(os.environ.get("MT5_LOGIN", "0") or 0)

def read_log_text() -> str:
    if not log.exists():
        return ""
    raw = log.read_bytes()
    if raw[:2] == b"\xff\xfe" or (len(raw) > 4 and raw[1] == 0):
        return raw.decode("utf-16-le", "replace")
    return raw.decode("utf-8", "replace")

ok = False
for i in range(45):
    time.sleep(2)
    text = read_log_text()
    net_lines = [ln for ln in text.splitlines() if "Network" in ln or "authorized" in ln.lower() or "authorization" in ln.lower()]
    acct = {}
    age = 9999
    if bridge.exists():
        age = int(time.time() - bridge.stat().st_mtime)
        try:
            acct = json.loads(bridge.read_text(encoding="utf-8"))
        except Exception:
            acct = {}
    login = int(acct.get("login") or 0)
    bal = float(acct.get("balance") or 0)
    cur = str(acct.get("currency") or "")
    lev = int(acct.get("leverage") or 0)
    raw_conn = acct.get("terminal_connected_raw")
    print(
        f"t={i*2:02d}s log={log.stat().st_size if log.exists() else 0} "
        f"net_lines={len(net_lines)} login={login} bal={bal} cur={cur!r} lev={lev} "
        f"raw_conn={raw_conn} age={age}"
    )
    # Success: network auth line OR live money fields
    if any("authorized" in ln.lower() for ln in net_lines):
        print("SUCCESS: authorized line in journal")
        ok = True
        break
    if age < 30 and login > 0 and (cur or lev > 0 or bal != 0.0):
        print("SUCCESS: live account money/meta fields present")
        ok = True
        break
    if any("authorization" in ln.lower() and "fail" in ln.lower() for ln in net_lines):
        print("AUTH_FAILED:")
        for ln in net_lines[-8:]:
            print(" ", ln)
        break

print("--- journal tail ---")
print("\n".join(read_log_text().splitlines()[-25:]))
if bridge.exists():
    print("--- account.json ---")
    print(bridge.read_text())
raise SystemExit(0 if ok else 2)
PY

status=$?
if [[ "$status" -eq 0 ]]; then
  info "Force login path looks healthy. Check: uv run mt5-arch account"
  # optional mt5server for RPyC users
  if [[ -x "$SCRIPT_DIR/05-start-mt5server.sh" ]]; then
    "$SCRIPT_DIR/05-start-mt5server.sh" >/dev/null 2>&1 || true
  fi
  exit 0
fi

warn "Trade-server login did not confirm within timeout."
warn "Inspect: iconv -f UTF-16 -t UTF-8 \"$LOG\" | tail -40"
warn "If Journal has 'authorization failed', fix MT5_LOGIN/MT5_PASSWORD/MT5_SERVER in .env"
warn "If Journal has no Network lines, broker TCP/TLS under Wine is still blocked — try broker server list refresh in GUI"
exit 2
