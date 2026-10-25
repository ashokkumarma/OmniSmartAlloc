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
buffer → inbound credit → state (Abundant/Balanced/Tight/Critical) → margin-ranked allocation →
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
  web/                channels.html (storefronts) + ops.html (cockpit)
  register_sources.sql / register_channel_sources.sql   Zetaris registration (explicit approval)
  outbox/             agent action log (allocations, alerts, decisions)
scripts/              setup.py, validate_stack.py, register_demo_sources.py
tests/                38 offline tests (fake connectors; no external deps)
```

## Prerequisites

- Python 3.11+ (Windows: `py -3.12`)
- Docker Desktop (Zetaris stack + channel DB)
- Java JDK 11+ with `JAVA_HOME` set (for the Zetaris JDBC driver)
- The Zetaris platform bundle extracted at `./zetaris-platform/` (see hackathon materials; includes
  `jdbc/ndp-jdbc-driver-*.jar`)
- An NVIDIA NIM API key (https://build.nvidia.com) — model used: `nvidia/nemotron-3-ultra-550b-a55b`

## Installation

```bash
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt   # Windows
# or: .venv/bin/python -m pip install -r requirements.txt

# or run the idempotent setup script (venv + deps + checks):
py -3.12 scripts/setup.py
```

Create `.env` from `.env.example` and fill in:

| Variable | Where to get it |
|---|---|
| `NVIDIA_NIM_API_KEY` | https://build.nvidia.com → Nemotron model → Get API Key |
| `NEMOTRON_MODEL` | `nvidia/nemotron-3-ultra-550b-a55b` |
| `ZETARIS_USERNAME` / `ZETARIS_PASSWORD` | `ZETARIS_ADMIN_EMAIL` / `ZETARIS_ADMIN_PASSWORD` in `zetaris-platform/.env` |
| `ZETARIS_JDBC_JAR` | `zetaris-platform/jdbc/ndp-jdbc-driver-*.jar` |
| `CHANNELS_DB_PASSWORD` | any local password for the demo order DB (default `omni_demo_pw`) |

## Run the demo stack

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

One command for steps 2–4: `.venv\Scripts\python.exe scripts/start_demo.py`

First-time Zetaris source registration (writes to the instance — run once):

```bash
.venv\Scripts\python.exe scripts\register_demo_sources.py --execute                    # back-office sources
.venv\Scripts\python.exe scripts\register_demo_sources.py --file demo\register_channel_sources.sql --execute  # order sources
```

## Use it

- `http://localhost:8902/channels` — place orders on DTC / Amazon / Etsy / Walmart tabs
  (each writes to that channel's own system: 3 Postgres tables + 1 REST API)
- `http://localhost:8902/ops` — Dashboard / Orders / Inventory tabs: federated stock view,
  inbound shipments with projected dates, alerts, and **▶ Run allocation cycle** (runs the real agent)
- CLI: `.venv\Scripts\python.exe -m src.main "Run the allocation cycle for all four SKUs" --show-trace`
- Validate: `.venv\Scripts\python.exe scripts\validate_stack.py` → expect 20 PASS / 0 FAIL
- Tests: `.venv\Scripts\python.exe -m pytest` → 38 passed

## Design guarantees

- **Read-only Zetaris** — every statement passes `ensure_read_only` (SELECT/SHOW/DESCRIBE/WITH/EXPLAIN only)
- **Deterministic math** — the LLM never computes numbers; `compute_allocation` does
- **Guardrailed writes** — allocation caps, locked-SKU blocks, missing-data fallbacks, zero/negative
  margin protection, human escalation for POs/price changes
- **Explainable output** — one JSON record per SKU with reasoning, risks, `guardrails_checked`, plus
  a ≤4-sentence summary (see the system prompt in `src/prompts/omnismartalloc.py`)
