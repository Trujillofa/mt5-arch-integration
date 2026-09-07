## Seven Desk (browser copy terminal)

Read-only multi-account paper desk with a WSF live fetch. Nested at
[`apps/seven-desk`](../apps/seven-desk). It uses `config/brokers/wsf.env` (login/server
only) and, when the Wine terminal + Mt5ArchBridge EA are running, the same
`account.json` / `positions.json` / `deals_export.csv` snapshots as `mt5-arch account`.
Paper copy is the default and never live-OrderSends. WSF live fetch is optional
and fails closed when the prefix or bridge is absent. A separate fail-closed
path `POST /api/wsf/order` can send a min-lot scratch on WSF 149736 only when
the body has `{ "live": true, "confirm": "WSF-149736" }`. Arm **WSF live copy**
or **FundedNext live copy** or **Alpha Capital live copy** or **FundingPips live copy**
or **Neomaa live copy** or **Fortraders live copy** on those cards
so slaves copy the **same type** as the ticket (market / limit / stop). Arm
**FTMO live master** so Place master trade is a real EURUSD send
on 541163357 (default **1.4** lots; FundedNext **0.35**; FundingPips **0.8**)
before any copy. Market Buy/Sell stay available; limit and stop are extra. Other books stay paper. The happy path is in-process
`Mt5ArchBridge` v1.25 polling `desk_live_order_request.txt` (seconds).
One-shots restore the branded
terminal in the background and refuse a generic `Program Files/MetaTrader 5`
tree inside those prefixes (that leftover can carry another company’s
`account.json`). Restore writes `Mt5ArchBridge` onto the branded Default
chart (`InpBroker=wsf|ftmo|fundednext|alphacapital|fundingpips|neomaa|fortraders`) and restarts that book when
`heartbeat.txt` is stale, so fetch/probe can see a fresh snapshot again.
A stale heartbeat **blocks** the live EA path (JSON 409, no one-shot
fallback). Fetch/probe still fail closed on
a stale snapshot. An explicit `terminal_connected=false` (weekend FX /
Neomaaa-global down) refuses OrderSend immediately with JSON 409 — it does
not launch Wine. Live order HTTP handlers return JSON within ~70s even
when a one-shot is silent; they no longer `spawnSync` wine for up to
180s (that blocked the event loop and left Alpha Capital POSTs with no
body). Alpha one-shots log into `ACGMarkets-Main` (not `ACGMarkets`).
A leftover `desk_live_order_request.txt` without a matching result is an
orphan: in-flight (younger than 90s) refuses a second OrderSend; stale
orphans are deleted. The EA claims `request_id` before OrderSend
and will not re-process the same id after a restart.
Omit `order_type` and the send is **market**. Pending types are
`buy_limit` / `sell_limit` / `buy_stop` / `sell_stop`. Omit `price` on a
pending and the EA uses a **50-point** offset from bid/ask (5.0 pips on
5-digit FX) so a limit stays passive and a stop stays on the trigger side.
An explicit typed price is sent even if it is on the wrong side of the
market. Volume above 0.01 requires `volume_confirm: true`.
Default lots are **1.4** except FundedNext **0.35** and FundingPips **0.8**.
`volume_min: true` is the explicit 0.01 override. Hard max is 10 lots.
`action: "cancel"` plus optional `ticket` removes a pending order
(`TRADE_ACTION_REMOVE`). CLOSE / flatten cancels working limits, not only
positions. Already-flat (`no open … desk position`, `no pending desk order
to cancel`, or `position vanished`) drops the desk row the same as `ok`.
If the EA heartbeat is stale, trade is not allowed, or the build is older
than v1.25, the route returns JSON **409** and does **not** fall back to a
wine one-shot. It never talks to Vantage, FP, or official MCP on :22346.

```bash
cd ~/Projects/trading/mt5-arch-integration
./scripts/20-seven-desk.sh            # host systemd --user keep-alive on :3847
./scripts/20-seven-desk.sh --status
./scripts/20-seven-desk.sh --stop
# or: systemctl --user status|stop|start seven-desk.service
# http://127.0.0.1:3847
```

`20` installs `ops/systemd/seven-desk.service` into `~/.config/systemd/user/`
and `enable --now`s it (`Restart=always`). Host next, not Podman — the desk
orchestrates Wine / `scripts/21` / file-bridge on the host. It leaves :3847
alone if HTTP 200 is already up. After reboot it comes back when user linger
is on (`WantedBy=default.target`). A Cursor PTY `npm run dev` dies with the
session.
