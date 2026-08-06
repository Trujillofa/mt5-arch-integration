let meta = #{
    name: "mt5-net-fix",
    description: "Run remaining MT5 Wine trade-auth fix recommendations and measure Pass A/B",
    when_to_use: "MT5 Journal Network silent, balance 0, empty currency/leverage under Wine",
    phases: [
        #{ title: "Diagnose", detail: "baseline Network/account/sockets" },
        #{ title: "Bridge-down", detail: "sudo down docker0/br-* + force-login" },
        #{ title: "Wine-TLS", detail: "winhttp/schannel registry experiments" },
        #{ title: "Hardening", detail: "script guards + offline suite" },
        #{ title: "Report", detail: "write Pass A/B evidence" },
    ],
};

let attempt_schema = #{
    "type": "object",
    "required": ["name", "pass_a", "network_count", "currency", "leverage", "notes"],
    "properties": #{
        "name": #{ "type": "string" },
        "pass_a": #{ "type": "boolean" },
        "network_count": #{ "type": "integer" },
        "currency": #{ "type": "string" },
        "leverage": #{ "type": "integer" },
        "src_ip_ok": #{ "type": "boolean" },
        "notes": #{ "type": "string" },
        "log_path": #{ "type": "string" },
    },
};

let report_schema = #{
    "type": "object",
    "required": ["pass_a", "summary", "evidence_path", "next_steps"],
    "properties": #{
        "pass_a": #{ "type": "boolean" },
        "summary": #{ "type": "string" },
        "evidence_path": #{ "type": "string" },
        "next_steps": #{ "type": "string" },
        "attempts": #{ "type": "array", "items": #{ "type": "string" } },
    },
};

let repo = if args == () { () } else { args.repo };
if repo == () {
    repo = "/home/yderf/Projects/trading/mt5-arch-integration";
}
let prefix = if args == () { () } else { args.wineprefix };
if prefix == () {
    prefix = "/home/yderf/.mt5-staging";
}

// ---------------------------------------------------------------------------
phase("Diagnose");
// ---------------------------------------------------------------------------
let diag_prompt = "";
diag_prompt += "You are fixing MT5 trade-server auth under Wine on Linux. ";
diag_prompt += "Repo: " + repo + ". Use WINEPREFIX=" + prefix + " for all MT5 measurements. ";
diag_prompt += "Run shell commands with the run_terminal_command tool. Do NOT place any live orders. ";
diag_prompt += "Never print MT5_PASSWORD or .env secrets.\n\n";
diag_prompt += "Tasks:\n";
diag_prompt += "1. wine --version; echo WINEPREFIX; ls terminal under prefix.\n";
diag_prompt += "2. Measure sockets: ss -tnp | rg 'wine|main|terminal' || true\n";
diag_prompt += "3. Read today's journal UTF-16 under prefix .../logs/YYYYMMDD.log; count lines containing Network; show last 20 lines.\n";
diag_prompt += "4. Read account.json under .../MQL5/Files/mt5_arch/ if present (currency, leverage, login, server, terminal_connected).\n";
diag_prompt += "5. Run: WINEPREFIX=" + prefix + " MT5_BACKEND=file uv run mt5-arch account; capture exit code.\n";
diag_prompt += "6. ip -br addr; docker ps --format '{{.Names}}'; tailscale status | head -3\n";
diag_prompt += "7. Write snapshot to " + repo + "/.net-fix-evidence/workflow-baseline.log\n\n";
diag_prompt += "Return JSON fields: name='baseline', pass_a=true only if currency non-empty AND leverage>0, ";
diag_prompt += "network_count, currency, leverage, src_ip_ok (true if sockets use 192.168.x not 172.x), notes, log_path.";

let baseline = agent(diag_prompt, #{
    label: "diagnose-baseline",
    capability_mode: "all",
    output_schema: attempt_schema,
});

let attempts = [];
if baseline != () && baseline.success && baseline.output != () {
    attempts.push(baseline.output.name + ": pass_a=" + baseline.output.pass_a.to_string()
        + " net=" + baseline.output.network_count.to_string()
        + " cur=" + baseline.output.currency);
    if baseline.output.pass_a == true {
        log("Already Pass A at baseline — skip fix attempts");
        let early = "";
        early += "# Workflow early Pass A\n\nBaseline already live.\n";
        early += json_encode(baseline.output);
        let ep = write_scratch_file("report.md", early);
        complete(#{ pass_a: true, summary: "Already Pass A", evidence_path: ep, next_steps: "none", attempts: attempts });
    }
} else {
    attempts.push("baseline: failed or empty");
    log("Baseline agent failed; continuing fix attempts");
}

// ---------------------------------------------------------------------------
phase("Bridge-down");
// ---------------------------------------------------------------------------
let br_prompt = "";
br_prompt += "Repo: " + repo + ". Goal: try the remaining escalation of bringing Docker bridge ifaces DOWN (not just containers) ";
br_prompt += "during MT5 force-login, then measure Network/auth. Use WINEPREFIX=" + prefix + ".\n";
br_prompt += "Constraints: no live orders; never print passwords; ALWAYS restore docker bridges + containers + tailscale even on failure (script trap should do this).\n\n";
br_prompt += "Steps (use run_terminal_command, long timeout ~300000ms for the main script):\n";
br_prompt += "1. chmod +x " + repo + "/scripts/15-bridge-down-and-login.sh\n";
br_prompt += "2. cd " + repo + " && export WINEPREFIX=" + prefix + " WINEARCH=win64 DISPLAY=:0 && unset WAYLAND_DISPLAY MT5_TERMINAL_PATH && ";
br_prompt += "./scripts/15-bridge-down-and-login.sh --wait-sec=60\n";
br_prompt += "3. If script missing/fails, manually: docker stop all; tailscale down; sudo -n ip link set docker0 down; ";
br_prompt += "for each br-* UP iface sudo -n ip link set NAME down; then ./scripts/13-force-login-bridge.sh; wait 60s; measure; ";
br_prompt += "then restore all bridges up, tailscale up, docker start saved ids.\n";
br_prompt += "4. Parse Network count from journal, account.json currency/leverage, ss source IPs.\n";
br_prompt += "5. Append results to " + repo + "/.net-fix-evidence/workflow-bridge-down.log\n\n";
br_prompt += "Return JSON: name='bridge-down', pass_a, network_count, currency, leverage, src_ip_ok, notes, log_path.";

let bridge = agent(br_prompt, #{
    label: "try-bridge-down",
    capability_mode: "all",
    output_schema: attempt_schema,
});

if bridge != () && bridge.success && bridge.output != () {
    attempts.push(bridge.output.name + ": pass_a=" + bridge.output.pass_a.to_string()
        + " net=" + bridge.output.network_count.to_string()
        + " cur=" + bridge.output.currency);
    if bridge.output.pass_a == true {
        log("Pass A after bridge-down");
        let okp = write_scratch_file("report.md", "# Pass A via bridge-down\n\n" + json_encode(bridge.output));
        complete(#{
            pass_a: true,
            summary: "Pass A after docker bridge iface down + force-login",
            evidence_path: okp,
            next_steps: "Consider documenting as required login prep; keep WINEPREFIX default until user promotes staging",
            attempts: attempts,
        });
    }
} else {
    attempts.push("bridge-down: failed or empty");
}

// ---------------------------------------------------------------------------
phase("Wine-TLS");
// ---------------------------------------------------------------------------
let tls_prompt = "";
tls_prompt += "Repo: " + repo + ". WINEPREFIX=" + prefix + ". Previous attempts left trade Network at 0 with ESTAB Send-Q stalls. ";
tls_prompt += "Try Wine TLS/HTTP stack tweaks, then force-login and measure. No live orders; no password logging.\n\n";
tls_prompt += "Steps:\n";
tls_prompt += "1. Ensure crypt32=builtin (not native). Show: wine reg query 'HKCU\\Software\\Wine\\DllOverrides' 2>/dev/null | head\n";
tls_prompt += "2. Set overrides if needed: WINEDLLOVERRIDES and reg: winhttp=builtin, crypt32=builtin, secur32=builtin, bcrypt=builtin\n";
tls_prompt += "   Example: WINEPREFIX=" + prefix + " wine reg add 'HKCU\\Software\\Wine\\DllOverrides' /v crypt32 /t REG_SZ /d builtin /f\n";
tls_prompt += "   Same for winhttp, secur32, bcrypt.\n";
tls_prompt += "3. Optional: disable proxy in common.ini / auto_login already ProxyEnable=0.\n";
tls_prompt += "4. Kill wineserver+terminal, then: cd " + repo + " && export WINEPREFIX=" + prefix + " DISPLAY=:0 && ./scripts/13-force-login-bridge.sh\n";
tls_prompt += "5. Wait ~70s. Measure Network count, account currency/leverage, ss Send-Q and src IP.\n";
tls_prompt += "6. Also try one WINEDEBUG=+secur32,+winhttp,+winsock short capture for 15s only if Network still 0; ";
tls_prompt += "grep for connect failed / STATUS_ / schannel / certificate errors; save head of findings to evidence (no secrets).\n";
tls_prompt += "7. Write " + repo + "/.net-fix-evidence/workflow-wine-tls.log\n\n";
tls_prompt += "Return JSON: name='wine-tls', pass_a, network_count, currency, leverage, src_ip_ok, notes, log_path.";

let tls = agent(tls_prompt, #{
    label: "try-wine-tls",
    capability_mode: "all",
    output_schema: attempt_schema,
});

if tls != () && tls.success && tls.output != () {
    attempts.push(tls.output.name + ": pass_a=" + tls.output.pass_a.to_string()
        + " net=" + tls.output.network_count.to_string()
        + " cur=" + tls.output.currency);
    if tls.output.pass_a == true {
        log("Pass A after wine-tls");
        let ok2 = write_scratch_file("report.md", "# Pass A via wine-tls\n\n" + json_encode(tls.output));
        complete(#{
            pass_a: true,
            summary: "Pass A after Wine TLS/DLL override tweaks",
            evidence_path: ok2,
            next_steps: "Keep successful overrides in docs; do not force native crypt32",
            attempts: attempts,
        });
    }
} else {
    attempts.push("wine-tls: failed or empty");
}

// ---------------------------------------------------------------------------
phase("Hardening");
// ---------------------------------------------------------------------------
let hard_prompt = "";
hard_prompt += "Repo: " + repo + ". Harden scripts and verify offline suite stays green after net-fix work.\n";
hard_prompt += "1. Read scripts/lib.sh find_terminal64 — confirm it prefers active WINEPREFIX over config/local.paths.\n";
hard_prompt += "2. Read scripts/13-force-login-bridge.sh — confirm it kills wineserver and refuses terminal outside WINEPREFIX.\n";
hard_prompt += "3. If either check fails, patch surgically and re-check.\n";
hard_prompt += "4. Ensure scripts/15-bridge-down-and-login.sh is executable and has set -euo pipefail + restore trap.\n";
hard_prompt += "5. Run offline: cd " + repo + " && uv run pytest -q && uv run ruff check src tests\n";
hard_prompt += "6. Final measure with WINEPREFIX=" + prefix + " MT5_BACKEND=file uv run mt5-arch ping/account (expect exit 2 if still offline).\n";
hard_prompt += "7. Append hardening notes to " + repo + "/.net-fix-evidence/workflow-hardening.log\n\n";
hard_prompt += "Return JSON: name='hardening', pass_a (from live account fields only), network_count, currency, leverage, src_ip_ok, notes, log_path.";

let hard = agent(hard_prompt, #{
    label: "hardening-verify",
    capability_mode: "all",
    output_schema: attempt_schema,
});

if hard != () && hard.success && hard.output != () {
    attempts.push(hard.output.name + ": pass_a=" + hard.output.pass_a.to_string()
        + " net=" + hard.output.network_count.to_string()
        + " notes_len_ok");
} else {
    attempts.push("hardening: failed or empty");
}

// ---------------------------------------------------------------------------
phase("Report");
// ---------------------------------------------------------------------------
let rep_prompt = "";
rep_prompt += "Synthesize MT5 net-fix workflow results into durable evidence.\n";
rep_prompt += "Repo: " + repo + ". Read files under " + repo + "/.net-fix-evidence/workflow-*.log and phase4-*.log if present.\n";
rep_prompt += "Also read " + repo + "/.net-fix-evidence/SUMMARY.md and update it with a new Phase 4 section covering:\n";
rep_prompt += "- bridge iface down attempt (result)\n";
rep_prompt += "- wine TLS/DLL attempt (result)\n";
rep_prompt += "- whether Pass A was achieved\n";
rep_prompt += "- offline suite status\n";
rep_prompt += "- remaining escalations (broker installer, Windows VM)\n";
rep_prompt += "Do not claim Pass A without currency non-empty AND leverage>0 from account.json or CLI.\n";
rep_prompt += "Update " + repo + "/docs/TROUBLESHOOTING.md briefly if bridge-down recipe should be documented.\n";
rep_prompt += "Write final markdown to " + repo + "/.net-fix-evidence/WORKFLOW-REPORT.md\n\n";
rep_prompt += "Attempt rollup (may be incomplete): " + json_encode(attempts) + "\n\n";
rep_prompt += "Return JSON: pass_a, summary, evidence_path (WORKFLOW-REPORT.md path), next_steps, attempts (string array).";

let report = agent(rep_prompt, #{
    label: "write-report",
    capability_mode: "all",
    output_schema: report_schema,
});

let pass_a = false;
let summary = "Workflow finished without structured report";
let evidence_path = "";
let next_steps = "See .net-fix-evidence/";
if report != () && report.success && report.output != () {
    pass_a = report.output.pass_a;
    summary = report.output.summary;
    evidence_path = report.output.evidence_path;
    next_steps = report.output.next_steps;
    if report.output.attempts != () {
        // keep agent rollup if provided
        attempts = report.output.attempts;
    }
}

let body = "# mt5-net-fix workflow result\n\n";
body += "pass_a: " + pass_a.to_string() + "\n\n";
body += summary + "\n\n";
body += "evidence: " + evidence_path + "\n\n";
body += "next: " + next_steps + "\n\n";
body += "attempts:\n";
for a in attempts {
    body += "- " + a + "\n";
}
let scratch = write_scratch_file("report.md", body);
complete(#{
    pass_a: pass_a,
    summary: summary,
    evidence_path: evidence_path,
    next_steps: next_steps,
    attempts: attempts,
    scratch: scratch,
});
