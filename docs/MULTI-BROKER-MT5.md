# One MetaTrader 5 for any broker? Feasibility (this host + product model)

**Conclusion: partial — not “globally any broker with zero per-broker setup.”**

A single MT5 **binary** can host **multiple trade accounts** when each broker’s
**server is in that terminal’s server list** and credentials are valid.  
It is **not** possible to promise one Wine install trades every broker worldwide
without server discovery, correct company server names, and successful Wine
trade auth. Broker-branded installers are still often required in practice
because they pre-seed `servers.dat` and because Wine auth has been more reliable
on those builds on this host.

Evidence base: Arch Linux + Wine Staging 11.13, repo `mt5-arch-integration`,
journals under `~/.mt5*`, `.net-fix-evidence/SUMMARY.md` (2026-08-01).

---

## What “without each program” can mean

| Model | Meaning | Feasibility |
|-------|---------|-------------|
| **(a) One terminal binary / one Wine prefix / multi-account login** | Log into WSF, later switch login to Vantage (or keep both accounts in Navigator) inside **one** process, when both servers exist in that terminal’s list | **Conditional** — product supports multi-account; needs server list + working Wine network path |
| **(b) Concurrent multi-broker sessions** | Two live trade sessions at once (two companies) | **Conditional** — usually **two processes** (two prefixes or two terminals); one process is one active trade session for EA/bridge simplicity |
| **(c) Per-broker server-list / branding** | Broker installer only ships branding + `servers.dat` | **Not optional for “any” broker** — without the server endpoint name, login cannot succeed |

---

## Live evidence on this machine

| Path | Result |
|------|--------|
| `~/.mt5-wsf` — **WSFmarkets MT5 Terminal** | Login **149736** → `WSFmarkets-Server` → Journal **`authorized`** (demo, hedging) |
| `~/.mt5-vantage` — **Vantage International MT5** | Login **27496181** → **`VantageMarkets-Live 5`** → Journal **`authorized`**, CLI Pass A (`currency=USD`, `leverage=500`) |
| `~/.mt5-fpmarkets` — **FP Markets MT5 Terminal** | Login **84076984** → **`FPMarketsSC-Live`** → Journal **`authorized`**, live Pass A (`currency=USD`, `leverage=500`) |
| Cross-login | `27496181` on **`WSFmarkets-Server`** → **`Invalid account`** (wrong company/server) |
| `~/.mt5` generic MetaQuotes portable | Long stretches with **Network count 0** under Wine (auth path failed before broker reply) |

Sources:

- Journals:  
  `~/.mt5-wsf/.../logs/YYYYMMDD.log`,  
  `~/.mt5-vantage/.../logs/YYYYMMDD.log`
- Platform summary: `.net-fix-evidence/SUMMARY.md` (Phases 5–7)
- Profiles: `config/brokers/wsf.env`, `config/brokers/vantage.env`
- Switcher: `scripts/16-use-broker.sh`, CLI `mt5-arch brokers`

---

## Product reality (MetaTrader 5)

1. **Trade login is always to a named trade server**, not “to MetaQuotes in general.”
2. Broker installers typically install the same MT5 engine under a **brand folder** and ship a **pre-seeded server list** (`Config/servers.dat` sizes differ markedly: Vantage ≫ WSF on this host).
3. Adding another broker to an existing terminal means **adding that server** (search/import in login UI, or using a build that already contains it)—not installing a different trading protocol.
4. Credentials for broker A never authorize on broker B’s server (observed: Invalid account).

So “one program for any broker” is really:

> one MT5 client that can discover or already contains the target server,  
> plus a Wine environment that completes Network auth for that path.

---

## Platform recommendation (this repo)

### Prefer today (proven)

- **One Wine prefix per broker brand that you actually trade**, with profiles:

  ```bash
  ./scripts/16-use-broker.sh vantage   # or wsf
  uv run mt5-arch brokers              # list profiles
  export WINEPREFIX=... MT5_BACKEND=file
  uv run mt5-arch account
  ```

- File bridge (`Mt5ArchBridge`) per prefix; do not expect one `account.json` for two live brokers without two bridges/processes.

### Reasonable experiment (conditional)

- On a **working** brand terminal (e.g. Vantage Pass A), try **File → Login → find another broker’s server** and add a second account.
  - If the server is discoverable and Wine auth works → multi-account in **one** prefix succeeds.
  - If the server is missing → you still need discovery (or that broker’s installer once to harvest/copy server list—not because the protocol differs).

### Do not promise

- “Install once, every broker worldwide forever” without server list + credentials + Wine Network success.
- That generic MetaQuotes portable alone will always auth (this host often had **silent Network=0**).
- That file-bridge + one process can be two concurrent live accounts without design work.

### Optional next engineering (out of scope of pure analysis)

1. Document GUI steps to “Add server” / multi-account on a Pass A terminal.
2. Keep `config/brokers/*.env` as the source of truth for login/server/prefix.
3. Only merge prefixes if multi-account auth is proven for the needed server pairs.

---

## Direct answer

| Question | Answer |
|----------|--------|
| Can one MT5 install serve **multiple brokers** without a **new** branded installer every time? | **Sometimes yes** — if you can add those brokers’ **servers** into that terminal and Wine can auth. |
| Can one install serve **any** broker with **zero** broker-specific setup? | **No.** Server list + credentials + working trade Network are required. |
| Should this platform drop per-broker prefixes immediately? | **No** — keep proven `~/.mt5-vantage` / `~/.mt5-wsf` until multi-account on one prefix is verified for your pairs. |

**Bottom line:** MetaTrader is already multi-account capable; it is not multi-company-by-magic. Brand installers are server-list/branding packages plus (on Wine) a more reliable auth path for those brokers—not separate “trading engines.”
