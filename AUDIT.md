# OmniSmartAlloc audit

Audit of `jason/polish` at tag `baseline-before-polish`. Scoring weights used for ranking: Impact 30, Technical 20,
Innovation 15, Demo 15, Product & UX 10, Sponsor tech 10. Deadline Oct 27, 23:45 UTC.

Tested here: storefront, Ops (all tabs), Reset, Scenario 1, order lifecycle, 43 unit tests, 10 smoke tests.
Not tested here (no Zetaris or model key on this machine yet): the agent run, the federated query panel, approvals.
Findings on those come from reading the code.

## 1. Bugs and broken flows

| # | Severity | What fails | Where | Fix |
|---|---|---|---|---|
| B1 | High (fixed) | Reset demo and Scenario 1 crashed on a fresh clone: `demo/outbox/` is gitignored and missing | `demo/server.py:232`, `demo/scenarios/seed_lamp002.py:166` | Fixed in `7902833` (create the folder first) |
| B2 | High | Ops KPIs are wrong: "200 total orders" when there are 885. Units ordered/shipped and the closed-orders charts are also computed from the truncated list | `demo/server.py:150` sends `orders[:200]`; `demo/web/ops.html:246`, `channels.html` charts count `S.orders` | Send totals computed server-side (counts and unit sums per channel/SKU/status) next to the 200 recent orders, and use them for KPIs and charts |
| B3 | High (demo) | No internet means no charts, and `renderSummary` throws at its first `new Chart` (`channels.html:153`), before it draws the data-sources diagram (`channels.html:187`) | `demo/web/channels.html:6`, `demo/web/ops.html:6` load Chart.js from jsDelivr | Vendor `chart.umd.min.js` 4.4.1 into `demo/web/` and serve it from `server.py` |
| B4 | Medium | The federated query panel shows the raw error `MissingSetting: Set ZETARIS_JDBC_URL…` in red when Zetaris is down | `demo/web/channels.html:208` | Show "Zetaris is not connected. Start it to see this live query." with a Retry button; keep the raw error in a tooltip |
| B5 | Medium | Reset demo on the Channels page shows no feedback at all (no busy state, no toast). The Ops page shows Scenario 1 and Generate history results in blocking `alert()` dialogs. (Correction: Reset itself takes about 0.3 s; an earlier version of this audit said 5–10 s without measuring.) | `channels.html:280`, `ops.html:454-474` | Busy state on the button and a toast when done, on both pages |
| B6 | Medium | Agent run failures are invisible: the button re-enables and nothing explains why. `_AGENT_JOB.tail` holds the output but the page never shows it | `demo/web/ops.html:476-481`, `demo/server.py:303` | Show the tail (or a short error) when `running` turns false without new decisions |
| B7 | Low | A model API error (timeout, 429, 5xx) raises out of the ReAct loop and kills the run | `src/agent/react.py:56` | Catch `openai.APIError`, retry once, then stop with a clear `stopped_reason` |
| B8 | Low | A guardrail is an `assert`, which Python drops under `-O` | `src/tools/allocation_tools.py:123` | Raise `ValueError` instead |
| B9 | Low | The UI server never loads `.env`, so a non-default `CHANNELS_DB_PASSWORD` in `.env` is ignored by the order store | `demo/order_stores.py:16` reads `os.environ` at import; `demo/server.py` never calls `load_dotenv` | Call `get_settings()` (which loads `.env`) before importing `order_stores` |
| B10 | Low | Using the app edits tracked files (`demo/data/*.json`), so teammates can commit demo state by accident | `demo/server.py:_save`, `seed_lamp002.py:_edit` | Click Reset before committing, or move runtime state out of tracked files (larger change; not recommended before the deadline) |

## 2. Code quality

- Duplicate logic: `scenario1()`, `genHistory()`, `resetDemo()` and `toast()` are copied in both `channels.html` and `ops.html`. One shared `demo/web/common.js` would remove about 40 lines.
- `channels.html` (295 lines) and `ops.html` (485 lines) are inline JS with inline styles on most elements. That is the main obstacle to any UI work.
- Missing error handling in the page scripts: every `fetch` assumes success. A failed `/api/state` leaves the page blank with no message (`channels.html:125`, `ops.html:217`).
- Hardcoded values: SKU list in the agent prompt (`demo/server.py:297`), channel colours in both Python and JS (`server.py:39`, both HTML files).
- README test count was stale (fixed). README claims `validate_stack.py` → "20 PASS"; not verifiable here.
- Types: Python is well typed. Page JS has none (expected for inline scripts).

## 3. Security

| # | Severity | Issue | Where | Fix |
|---|---|---|---|---|
| S1 | Medium | The UI server binds `0.0.0.0` and sends `Access-Control-Allow-Origin: *`. Anyone on the same network (hackathon Wi-Fi, venue) can reset the demo, place orders, or start agent runs that spend model credits | `demo/server.py:315` (CORS), `demo/server.py:375` (bind) | Bind `127.0.0.1` and drop the CORS header (the pages are same-origin). `mock_apis.py` must stay reachable from Docker, so leave it |
| S2 | Low | Agent alert text is inserted with `innerHTML` unescaped. It is model output built from data, so a crafted value in a source could inject HTML | `demo/web/ops.html:325` | Wrap fields in the existing `esc()` |
| S3 | Low | Federated error text is inserted unescaped | `demo/web/channels.html:208` | Use `textContent` |
| S4 | Low | `pytest` 8.4.2 has PYSEC-2026-1845 (fixed in 9.0.3). Dev-only. `requirements.txt` pins `<9` | `requirements.txt` | Needs your approval to change the pin |
| — | OK | No secrets in git history (only the local demo DB password, which is also the compose default). `.env` is ignored. SQL that includes a SKU is regex-validated first (`src/allocation/snapshot.py:19`). The read-only guard strips strings and comments before checking (`src/data_connectors/readonly.py`) |

## 4. Performance

- Reset: measured at 0.3 s. No change needed.
- `/api/state` reads every order from Postgres on each call. Fine at 885 orders; the page does not poll.
- The Ops dashboard renders all 200 orders in one list, making the page 8,675 px tall (see UI U3).
- Chart.js is the only external script, about 200 KB from the CDN.

## 5. Demo risk

| Risk | Where | Mitigation |
|---|---|---|
| No internet at demo time: no charts, broken page | B3 | Vendor Chart.js (15 minutes) |
| Zetaris down: red raw error on the main page | B4 | Friendly state |
| Agent run takes minutes with no visible progress (NIM 550B model, up to 25 steps); a rate limit or timeout fails silently | B6, B7 | Progress feed (feature F1) and a recorded run (F2) |
| Fresh database is empty until someone clicks Reset | `scripts/start_demo.py` | Seed automatically when the order tables are empty (small change; your call) |
| Someone on the network clicks Reset mid-demo | S1 | Bind to localhost |
| Wrong KPI ("200 total orders") visible on the first Ops screen | B2 | Server-side totals |

## 6. UI review (first 60 seconds as a judge)

What a judge sees now: a dark neon dashboard with four different gradient buttons in the header (purple, cyan, green, blue), five tabs, four charts, and a large "where the data lives" diagram. The diagram is the best part: it shows the Track 1 story (four channels in different systems, federated by Zetaris). The header has no clear first action.

| # | Screen | Now | Change | Why it helps a first-time user |
|---|---|---|---|---|
| U1 | Header (both pages) | 4 gradient buttons of equal weight, plus a link | One filled accent button per page ("Run allocation cycle" on Ops, "Scenario 1" on Channels); the others become quiet secondary buttons; Reset moves into a "Demo" menu | One obvious next step; Reset is destructive and should not look like the main action |
| U2 | Global | 6+ accent colours, emoji icons (⟳ ↺ ▶ ⚠ ✖ 🔒) | One accent (keep the indigo), semantic tokens for success/warning/danger, channel colours only on channel data; Lucide SVG icons | Colour then means something: status or channel, never decoration |
| U3 | Ops → Dashboard | 200-row order list; page is 8,675 px tall | Show the 10 most recent with "Show all orders →" linking to the Orders tab | The dashboard fits on one screen |
| U4 | Tabs (both pages) | Plain `<div>`s: no keyboard access, no screen-reader role | Segmented control built from `<button role="tab">` with `aria-selected`, arrow-key support, visible focus ring | Keyboard and screen-reader access; it also looks like a native control |
| U5 | Both pages at 375 px | Layout is 1,217 px (Channels) / 924 px (Ops) wide, zoomed out | Single-column below 900 px; charts full width; header buttons wrap | Readable on a phone or a judge's narrow window |
| U6 | Typography | Mixed weights and sizes, uppercase tracked labels everywhere | One family (Inter, falling back to system UI), scale 12/13/15/17/22/28/34, weights 400/600/700, line height 1.4–1.5 | Clear hierarchy |
| U7 | Spacing and surfaces | Mixed paddings, heavy borders on every card | 8-pt grid (8/16/24/32), one card style (12 px radius, 1 px hairline, subtle shadow), max content width 1280 px | Calmer and more premium |
| U8 | States | No loading state; Reset gives no feedback; raw errors | Skeleton cards while `/api/state` loads; busy state + toast on every action; friendly error messages | Users always know what is happening |
| U9 | Order status donut | Labels overlap ("8 (3%)" over the ring) | Hide labels under 5% and list them in the legend | Removes a visible glitch |
| U10 | Polish | No favicon (404 in console); titles fine | Add an SVG favicon | Removes the console error; looks finished |
| U11 | Motion | None (fine) | Only a 150–200 ms fade on tab change and toast; respect `prefers-reduced-motion` | Feels smooth without being showy |
| U12 | Accessibility | Many labels are 10.5–11 px muted text (chart axes, order timestamps, KPI captions) | Minimum 12 px text; check muted text reaches 4.5:1 | WCAG AA |

### Top 5 UI changes (wow ÷ effort)

| Rank | Change | Effort | Break risk | Touches |
|---|---|---|---|---|
| 1 | U1 header hierarchy: one primary button, Reset in a quiet menu | 1 h | Low | Header markup and CSS in both HTML files |
| 2 | U3 dashboard order list limited to 10 + link | 0.5 h | Low | `ops.html` render of `allOrders` |
| 3 | U8 + B4 + B5 feedback states: busy buttons, toasts, friendly Zetaris-down message | 1.5 h | Low | Page JS only; no API change |
| 4 | U2 + U6 + U7 token pass: one accent, one type scale, one card style, Lucide icons | 3–4 h | Medium (visual only; touches most markup) | CSS in both HTML files |
| 5 | U4 + U5 accessible tabs and single-column layout under 900 px | 2–3 h | Medium | Tab markup, CSS media queries |

## 7. Features (max 5)

| # | Feature | User problem | Why judges notice | Effort | Break risk | Depends on |
|---|---|---|---|---|---|---|
| **F1 (top pick)** | **Live agent trace on Ops**: stream each step of the allocation run (tool, source queried, rows, guardrail hit) into a panel while it runs | Today the button just says "Agent running…" for minutes. The user cannot see the agent working across sources, which is the Track 1 story | Shows "discovers and works across fragmented sources" live: Impact, Demo and Sponsor tech | M (3–4 h) | Medium: `_run_agent` reads stdout line by line; `src/main.py` prints a JSON line per step (new flag, default off) | Zetaris + model key to test end to end |
| F2 | **Recorded run fallback**: save one complete agent run (trace + outbox) and replay it from the UI when Zetaris or the model is unavailable, clearly labelled "Recorded run" | Demo fails if the network, Zetaris or the model rate-limits | Keeps the demo working in any conditions | M (2–3 h) | Low: read-only replay of saved files | F1's trace format |
| F3 | **Sources-touched highlight**: after a run, light up the sources in the "where the data lives" diagram that the agent actually queried, with row counts | The diagram is static today | Makes federation visible in one glance | S (1–2 h) | Low | `AgentResult.sources_touched` already exists |
| F4 | **Stack health strip**: small status row for Postgres, source APIs, Zetaris and model key, with one-line fixes | Demo surprises: something is down and nobody knows which part | Looks production-ready; saves the demo | S (1–2 h) | Low: one new GET endpoint | — |
| F5 | **Export decision report**: download the latest allocation decisions with reasoning and guardrails as Markdown | Ops leads need to share why stock moved | Concrete user value | S (1 h) | Low | — |

## 8. Suggested build order before the deadline

B3, B2, S1, B4/B5 (all small and low risk) → UI top 1–3 → F1 → F3 → UI 4–5 if time remains.

## 9. Addendum: UI rebuild (React + GSAP)

The two HTML pages became one app in `demo/app` (React 19, TypeScript, GSAP, Chart.js, Lucide icons), served by
`demo/server.py` at `/`. No API, schema or data change: every call is the same request the old pages sent.
The original pages remain at `/classic/channels` and `/classic/ops`, and are served at `/`, `/ops`, `/channels` if the app is not built.

- **Structure:** sidebar (Overview, Orders, Inventory, Agent, Storefronts, Data sources), Ctrl+K search palette, demo-data actions in the sidebar (header bar on phones).
- **Design:** system font stack (SF Pro on Apple devices), 8-pt spacing, one accent, semantic tokens with light and dark from the OS, translucent sidebar and toolbar, 14 px cards, Lucide icons.
- **Motion (GSAP):** staggered view entrances, KPI count-up, meters that grow in, live agent-step rows, an animated data-flow diagram while Zetaris is connected, sheet and toast springs. Every animation is skipped under `prefers-reduced-motion`.
- **Service features:** a "Needs attention" queue on Overview (approvals, tight or critical stock, late inbound, waiting orders, Zetaris status), order search and status filters, bulk actions behind a confirmation sheet, sheets instead of `confirm()` / `prompt()`, a live status footer (stores, Zetaris, agent).
- **Resolved from this audit:** U1–U12 (header hierarchy, long order list, accessible tabs, 375 px layout, type scale, states, favicon, contrast) and F1 (live agent trace) in the new app.
- **Accessibility:** tabs are real `role="tab"` controls with arrow keys; dialogs trap and restore focus and close on Escape; icon-only controls and charts have labels; text contrast checked against WCAG AA.
- **Build:** `scripts/start_demo.py` runs `npm ci && npm run build` once (Node 20+). Without Node it serves the original pages. `demo/app/node_modules` and `dist` are git-ignored.
