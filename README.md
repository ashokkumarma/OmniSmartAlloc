# OmniSmartAlloc

**Open Agent Hackathon 2026 — Track 1: Solving Fragmented Intelligence**

An autonomous inventory-allocation agent that reasons across data sources that were never designed to
work together. Orders, stock, supplier reliability, channel economics and business rules each live in
their own system; a **NVIDIA Nemotron** ReAct agent federates them through **Zetaris** and produces
guardrailed, explainable per-channel allocations for a multi-channel seller (DTC, Amazon, Etsy, Walmart).

## Why this is Track 1

The agent cannot answer "should I allocate, and where?" from any single source:

| Source | Type | Holds |
|---|---|---|
| `CHANNEL_DB` | **Postgres via JDBC** | `dtc_orders`, `etsy_orders`, `walmart_orders` |
| `AMAZON_API` | **REST** | Amazon seller orders |
| `WMS` | REST | inventory, inbound POs |
| `SUPPLIER_PORTAL` | REST | supplier on-time %, lane delays |
| `CHANNEL_ANALYTICS` | REST | margin, velocity, demand confidence per channel |
| `RULES_ENGINE` | REST | locked/protected SKUs, floors, promos |

Zetaris exposes all of them as queryable tables (`omnismart.*`, `CHANNEL_DB.*`); a single Lightning SQL
statement can `UNION` a Postgres table with a REST response. The agent runs read-only SQL through a
`ensure_read_only` guard and all arithmetic happens in a deterministic engine (`src/allocation/engine.py`) —
sellable (on-hand minus committed) → inbound credit → state (Abundant/Balanced/Tight/Critical) → margin-ranked allocation →
25% per-run change limit → guarded write to `demo/outbox/`.

## Repository layout

```
src/                  agent (ReAct loop, tools, LLM, connectors, prompts)
  allocation/         deterministic engine + Zetaris snapshot loader
  tools/              run_query, discovery, allocation, action tools
demo/
  data/               seed JSON for the mock source APIs + catalog
  channels_db/        Postgres schema (dtc/etsy/walmart order tables)
  docker-compose.channels.yml   channel order DB container
  mock_apis.py        REST source APIs (port 8901)
  order_stores.py     per-channel order persistence
  server.py           demo UI server (port 8902)
  app/                React + TypeScript + GSAP UI (built to app/dist, served by server.py)
  web/                the original channels.html + ops.html (kept at /classic/*; used if the app is not built)
  register_sources.sql / register_channel_sources.sql   Zetaris registration (explicit approval)
  outbox/             agent action log (allocations, alerts, decisions)
scripts/              setup.py, validate_stack.py, register_demo_sources.py
tests/                46 offline tests (fake connectors; no external deps)
```

## Run it locally

### Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| Python | 3.11+ (tested on 3.12 and 3.14) | everything |
| Node.js | 20+ with npm (tested on 24) | builds the UI on first run; without it the original pages are served |
| Docker Desktop | current | channel order DB (any Postgres 16 on `127.0.0.1:5433` also works) and the Zetaris stack |
| Java JDK | 11+ (tested on 21), with `JAVA_HOME` set | Zetaris JDBC driver (agent runs only) |
| Zetaris platform bundle | from the hackathon materials, extracted to `./zetaris-platform/` | agent runs and the federated query panel |
| NVIDIA NIM API key or Meterless Runtime token | — | agent runs |

The storefront and ops screens, Reset demo, Scenario 1 and order flows need only Python and Postgres.
Agent runs need Zetaris and a model key as well.

### Setup

```bash
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt   # Windows
# or: .venv/bin/python -m pip install -r requirements.txt

# or run the idempotent setup script (venv + deps + checks):
py -3.12 scripts/setup.py

copy .env.example .env      # Windows; cp on macOS/Linux. Then fill in the values below.
```

### Run

```bash
.venv\Scripts\python.exe scripts/start_demo.py
```

This builds the UI on first run (`npm ci` and `npm run build` in `demo/app`), starts the channel order DB
(skipped if one already answers on port 5433), the source REST APIs on port 8901, and the demo UI.
Open **http://localhost:8902** for the landing page, or **http://localhost:8902/app** for the app, and choose **Reset demo** in the sidebar once to load the baseline orders.

To work on the UI with hot reload: keep the demo running, then `cd demo/app && npm install && npm run dev`
and open http://localhost:5173 (API calls are forwarded to port 8902).

### Configuration

Fill in `.env`:

| Variable | Where to get it |
|---|---|
| `NVIDIA_NIM_API_KEY` | https://build.nvidia.com → Nemotron model → Get API Key |
| `NEMOTRON_MODEL` | `nvidia/nemotron-3-ultra-550b-a55b` |
| `ZETARIS_USERNAME` / `ZETARIS_PASSWORD` | `ZETARIS_ADMIN_EMAIL` / `ZETARIS_ADMIN_PASSWORD` in `zetaris-platform/.env` |
| `ZETARIS_JDBC_JAR` | `zetaris-platform/jdbc/ndp-jdbc-driver-*.jar` |
| `CHANNELS_DB_PASSWORD` | any local password for the demo order DB (default `omni_demo_pw`) |

### Run each service separately

```bash
# 1. Zetaris platform
cd zetaris-platform && docker compose up -d && cd ..

# 2. Channel order DB (Postgres: DTC / Etsy / Walmart tables)
docker compose -f demo/docker-compose.channels.yml up -d

# 3. Source REST APIs (WMS, supplier portal, channel analytics, rules, Amazon orders)
.venv\Scripts\python.exe demo/mock_apis.py 8901

# 4. Demo UI -> http://localhost:8902
.venv\Scripts\python.exe demo/server.py
```

`scripts/start_demo.py` runs steps 2–4 for you.

First-time Zetaris source registration (writes to the instance — run once):

```bash
.venv\Scripts\python.exe scripts\register_demo_sources.py --execute                    # back-office sources
.venv\Scripts\python.exe scripts\register_demo_sources.py --file demo\register_channel_sources.sql --execute  # order sources
```

## Use it

A landing page at `http://localhost:8902/` and the app at `/app`, with a sidebar and a search palette (Ctrl+K / ⌘K). **Theme** in the top bar (under **Menu** on phones) switches Auto, Light and Dark; Auto follows the OS.

| Section | URL | What it does |
|---|---|---|
| Landing page | `/` | What the product does: a 3D view of the channel caps (a pool of stock circled by four rings, each lit to its channel's cap), a pinned step-by-step story and smooth scrolling |
| Overview | `/app` (also `/ops`) | KPIs, what needs attention, stock health per SKU, charts, recent orders, the live **Agent run** trace |
| Orders | `/orders` | Every order in one queue: filter, search, fulfil, split (partial), cancel, bulk actions |
| Inventory | `/inventory`, `/inventory/<SKU>` | Stock per SKU, channel allocations, inbound shipments with projected arrival, days of cover. A product page shows its cap rails, inbound POs, agent notes and open orders |
| Agent | `/agent` | How channels are ranked, every decision with its savings maths, **Approve** / **Deny** held changes |
| Storefronts | `/storefronts` (also `/channels`) | Place orders on DTC / Amazon / Etsy / Walmart; each writes to that channel's own system (3 Postgres tables + 1 REST API) |
| Data sources | `/sources` | The fragmented-sources-to-Zetaris diagram and the live federated SQL query |

**Run allocation cycle** (top right) runs the real agent. The Agent run card shows its status (queued, running, waiting for you, done, failed), elapsed time, each step, a lamp for every system it has read, and **Run again** after a failure. The original pages are still served at
`/classic/channels` and `/classic/ops`.
- CLI: `.venv\Scripts\python.exe -m src.main "Run the allocation cycle for all four SKUs" --show-trace`
- Validate: `.venv\Scripts\python.exe scripts\validate_stack.py` → expect 20 PASS / 0 FAIL
- Tests: `.venv\Scripts\python.exe -m pytest` → 46 passed

## Design guarantees

- **Read-only Zetaris** — every statement passes `ensure_read_only` (SELECT/SHOW/DESCRIBE/WITH/EXPLAIN only)
- **Deterministic math** — the LLM never computes numbers; `compute_allocation` does
- **Guardrailed writes** — allocation caps, locked-SKU blocks, missing-data fallbacks, zero/negative
  margin protection, human escalation for POs/price changes
- **Explainable output** — one JSON record per SKU with reasoning, risks, `guardrails_checked`, plus
  a ≤4-sentence summary (see the system prompt in `src/prompts/omnismartalloc.py`)
