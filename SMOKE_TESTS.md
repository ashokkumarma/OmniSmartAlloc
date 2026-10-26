# Smoke tests

Run these after every change. Start the stack first: `.venv\Scripts\python.exe scripts/start_demo.py`.

## Automated

```bash
.venv\Scripts\python.exe -m pytest            # 46 offline unit tests (no stack needed)
.venv\Scripts\python.exe -m pytest smoke      # 12 HTTP smoke tests against the running stack (~1.5 min)
```

The smoke suite resets the demo before and after, so `demo/data/*.json` ends unchanged. It covers routing (app and original pages), asset serving and path traversal, reset, orders, validation and Scenario 1. Build the UI first (`cd demo/app && npm ci && npm run build`) or those checks fall back to the original pages.
Base URLs can be changed with `OMNI_UI_URL` and `OMNI_API_URL`.

## Manual (browser)

Open http://localhost:8902 and check the browser console after each flow (expected: no errors; no requests outside localhost).
The sidebar becomes a scrolling bar under the header below 960 px; every action is still there.

| # | Flow | Steps | Expected result | Needs |
|---|---|---|---|---|
| 1 | App loads | Open `/`, then click each sidebar item | Overview, Orders, Inventory, Agent, Storefronts, Data sources render; page title changes; charts draw (Chart.js is bundled, no internet needed); `/ops` and `/channels` open Overview and Storefronts | Postgres |
| 2 | Reset demo | Sidebar → **Reset demo**, confirm in the sheet | Button shows "Resetting…"; toast "Demo reset: 885 orders restored"; Overview shows 885 total orders | Postgres |
| 3 | Place an order | Storefronts → DTC → MUG-001, qty 1 → **Buy** | Toast "Order placed … saved to Postgres (JDBC) CHANNEL_DB.dtc_orders"; order appears in the feed; Inventory shows MUG-001 reserved +1 | Postgres |
| 4 | Order validation | Buy more than the channel's allocation | Error toast naming the allocation limit; nothing saved | Postgres |
| 5 | Fulfil / partial / cancel | Orders → on an open order use **Fulfill all**, **Partial**, **Cancel** | Partial sheet only accepts 1 to remaining − 1 and previews the result; statuses change; stock updates; focus returns to the opener when a sheet closes | Postgres |
| 6 | Bulk actions | Orders → **Fulfill all open** / **Cancel all open** | Confirmation sheet with the count; all open orders update | Postgres |
| 7 | Filter and search | Orders → status tabs and the KPI tiles; search "Etsy" | Lists narrow; counts stay for all 885 orders | Postgres |
| 8 | Scenario 1 | Sidebar → **Scenario 1**, confirm | "Loading scenario…"; toast "Scenario 1 loaded … Checks: 10 passed, 1 failed" without Zetaris (11 passed with it) | Postgres |
| 9 | Generate history | Sidebar → **Generate history** | Toast "Generated N orders"; charts update. Reset demo afterwards | Postgres |
| 10 | Search palette | Press Ctrl+K, type "inven", Enter | Opens Inventory; Esc closes; arrow keys move the selection | — |
| 11 | Zetaris down | Data sources, with Zetaris stopped | "Zetaris is not connected" with a **Retry** button; sidebar shows Zetaris "not connected"; Overview lists it under Needs attention | — |
| 12 | Federated query | Data sources, with Zetaris running | Table of the 4 channels from one Lightning SQL statement; connector dots animate | Zetaris |
| 13 | Run allocation cycle | **Run allocation cycle** (top right) | "Agent run" card appears on Overview and Agent, one row per step (what it did, sources read) while it runs; ends "Last run · N steps · finished"; new decisions and alerts. Without a model key: toast "The agent run did not finish: Configuration error…" | Zetaris + model key |
| 14 | Approve / deny | Agent → a **Needs approval** card | Approve writes the allocation; Deny opens a sheet that requires a reason; sidebar badge count drops | an agent run that escalated |
| 15 | Original pages | Open `/classic/ops` and `/classic/channels` | The previous UI still works | Postgres |
| 16 | Reduced motion | Enable "reduce motion" in the OS, reload | No entrance or counting animations; everything still works | — |
| 17 | Product page | Inventory → click a product name; or Ctrl+K, type a SKU | URL is `/inventory/<SKU>`; breadcrumb "Inventory / SKU"; cap rails per channel; reload keeps the page; an unknown SKU shows an empty state with a way back | Postgres |
| 18 | Run states | Run an allocation cycle; with no model key | Card shows Queued, then Running with a clock and source lamps; with a failure: Failed, the reason, **Run again** | model key (Failed path: none) |
| 19 | Landing page | Open `/` at 1440 px and at 375 px; scroll to the end | Floating nav; hero object turns slowly and tilts with the pointer; the first headline word cycles every few seconds; sections fade up once; the paper section reveals its sentence word by word while pinned; pillar rows switch the preview (hover, click, arrow keys); **Open the app** goes to `/app` without a page load; **Auto / Light / Dark** switches theme. With reduce motion on: still hero object, no cycling, full sentence shown | — |

Flows 12–14 cannot run without Zetaris and a model key.

## Screens to compare (before/after)

Overview, Orders, Inventory, Agent, Storefronts, Data sources, each at 1440 px and 375 px, in light and dark.
