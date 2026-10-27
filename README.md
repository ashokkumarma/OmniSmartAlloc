# OmniSmartAlloc

**Open Agent Hackathon 2026, Track 1: Solving Fragmented Intelligence**

OmniSmartAlloc is an inventory-allocation agent for a seller on four channels: DTC, Amazon, Etsy and
Walmart. Orders, stock, supplier reliability, channel economics and business rules each live in a
separate system. The agent queries them all through **Zetaris** and produces per-channel allocations
with guardrails and an explanation for each one.

- **Model:** an **NVIDIA Nemotron** ReAct agent served through **Meterless Nightshift** (the primary
  AI provider).
- **Memory:** the **Meterless H-MEM** engine remembers what human reviewers approved and denied, and
  recalls it on the next run.

**All data in this repository is synthetic.** The products, orders, suppliers, margins and rules were
made up for the demo; none of it is customer data.

- How each sponsor technology is used: [docs/SPONSOR_TECH.md](docs/SPONSOR_TECH.md)
- Zetaris Unified Semantic Layer walkthrough, with live results: [docs/ZETARIS_USL.md](docs/ZETARIS_USL.md)
- Sample inputs and outputs from real runs: [docs/SAMPLES.md](docs/SAMPLES.md)
- Developer notes: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)

## Why this is Track 1

No single source can answer "should I allocate, and where?":

| Source | Type | Holds |
|---|---|---|
| `CHANNEL_DB` | **Postgres via JDBC** | `dtc_orders`, `etsy_orders`, `walmart_orders` |
| `AMAZON_API` | **REST** | Amazon seller orders |
| `WMS` | REST | inventory, inbound POs |
| `SUPPLIER_PORTAL` | REST | supplier on-time %, lane delays |
| `CHANNEL_ANALYTICS` | REST | margin, velocity, demand confidence per channel |
| `RULES_ENGINE` | REST | locked/protected SKUs, floors, promos |

Zetaris exposes all of them as tables you can query (`omnismart.*`, `CHANNEL_DB.*`), so a single
Lightning SQL statement can `UNION` a Postgres table with a REST response. The agent runs read-only SQL
through the `ensure_read_only` guard. All arithmetic happens in a deterministic engine
(`src/allocation/engine.py`), in this order:

1. sellable stock (on hand minus committed);
2. inbound credit;
3. state (Abundant, Balanced, Tight or Critical);
4. margin-ranked allocation;
5. the 25% per-run change limit;
6. a guarded write to `demo/outbox/`.

## Sponsor technology at a glance

| | Where | How to check it |
|---|---|---|
| Zetaris (JDBC + 5 REST sources, schemastore views, USL + DQ) | `src/data_connectors/`, `demo/register_*.sql`, `demo/zetaris/` | `python demo/zetaris/run_usl.py demo/zetaris/usl_queries.sql` |
| Meterless Nightshift, the primary model provider | `src/llm.py` | `python scripts/validate_stack.py` (pings the runtime), `pytest tests/test_llm_provider.py` |
| Meterless H-MEM engine (decision memory) | `engines/hmem/`, `src/memory/hmem.py` | `npm --prefix engines/hmem run conformance` (13/13), `pytest tests/test_hmem_memory.py` |
| NVIDIA Nemotron (plans, calls tools, explains) | `src/agent/react.py`, `src/prompts/omnismartalloc.py` | `python -m src.main "Run the allocation cycle for all four SKUs" --show-trace` |

### H-MEM: the agent remembers human decisions

When a reviewer clicks **Approve** or **Deny** on a held proposal in Smart Allocation, the decision is
stored as an H-MEM memory. The memory records:

- the SKU and its channel moves;
- the decision, the reason and the reviewer;
- provenance: the approval id.

On the next run, `compute_allocation` recalls that SKU's memories, ranked by H-MEM's hybrid score. It:

- adds them to the reasoning;
- returns them to Nemotron as `recalled_memories`;
- shows them on the next proposal's card under **Recalled from memory**.

Approving a plan that was built on recalled memories marks those memories helpful, with the exact H-MEM
confidence delta written to the ledger. If Node is missing, the agent falls back to the approvals log.

The engine is a TypeScript implementation of the Meterless H-MEM spec in `engines/hmem`. It needs Node
22.18+ and no npm install. Its tests:

```bash
npm --prefix engines/hmem run conformance                     # official Meterless runner + vectors -> 13/13 checks passed
.venv\Scripts\python.exe -m pytest tests/test_hmem_memory.py  # deny/approve -> memory -> recall; fallback; conformance
```

## Repository layout

```
src/                  agent (ReAct loop, tools, LLM, connectors, prompts)
  allocation/         deterministic engine, Zetaris snapshot loader, agent log + approvals
  memory/             H-MEM decision memory (calls engines/hmem)
  tools/              run_query, discovery, allocation, action tools
engines/hmem/         Meterless H-MEM engine (TypeScript), CLI, official conformance runner + vectors
demo/
  data/               seed JSON for the mock source APIs + catalog (synthetic)
  baseline/           seeded sample history loaded by Reset demo (see below)
  channels_db/        Postgres schema (dtc/etsy/walmart order tables)
  docker-compose.channels.yml   channel order DB container
  mock_apis.py        REST source APIs (port 8901)
  order_stores.py     per-channel order persistence
  server.py           demo UI server (port 8902)
  app/                React + TypeScript UI (built to app/dist, served by server.py)
  web/                the classic OMS and IMS pages (served at /oms and /ims)
  zetaris/            Zetaris exploration queries, USL DDL + DQ rules, runner, captured results
  register_sources.sql / register_channel_sources.sql   Zetaris registration (explicit approval)
  outbox/             live agent output (gitignored): allocations, approvals, alerts, decisions, memory/
docs/                 sponsor tech, Zetaris USL, samples (+ raw records), development notes
scripts/              setup.py, validate_stack.py, register_demo_sources.py, start_demo.py
tests/                67 offline tests (fake connectors; the H-MEM tests also run the real engine on Node)
```

### Sample history vs live output

- `demo/baseline/` is **seeded sample history**, not live output. It holds the four starting
  allocations, one superseded proposal and earlier decision records and alerts, so that the dashboard
  has history on first load. **Reset demo** copies `demo/baseline/data` into `demo/data`, reloads
  `demo/baseline/orders.json` into the order stores, and copies `demo/baseline/outbox` into
  `demo/outbox` (`demo/baseline/save_baseline.py` refreshes the baseline).
- `demo/outbox/` is where **live output** goes, and it is gitignored. To produce live output:
  1. start the stack (below);
  2. choose **Reset demo**, then place orders or **Load Scenario 1**;
  3. click **Run allocation cycle**, or run the CLI command.

  Every agent run appends to `demo/outbox/*.jsonl`, and every review adds an H-MEM memory under
  `demo/outbox/memory/`.
- `docs/samples/` holds copies of real records from such runs; [docs/SAMPLES.md](docs/SAMPLES.md)
  explains them.

## Run it locally

### Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| Python | 3.11+ (tested on 3.12 and 3.14) | everything |
| Node.js | 22.18+ with npm (tested on 24) | the H-MEM engine and building the UI (without Node the agent falls back to the approvals log and the classic pages are served) |
| Docker Desktop | current | the channel order DB (any Postgres 16 on `127.0.0.1:5433` also works) and the Zetaris stack |
| Java JDK | 11+ (tested on 21), with `JAVA_HOME` set | Zetaris JDBC driver (agent runs only) |
| Zetaris platform bundle | from the hackathon materials, extracted to `./zetaris-platform/` | agent runs and the federated query panel |
| Meterless Nightshift | running locally (OpenAI-compatible runtime on `127.0.0.1:8088`) | agent runs (primary provider) |

The storefront and dashboard screens, Reset demo, Scenario 1 and the order flows need only Python and
Postgres. Agent runs also need Zetaris and Meterless Nightshift.

### Setup

```bash
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt   # Windows
# or: .venv/bin/python -m pip install -r requirements.txt

# or run the idempotent setup script (venv + deps + checks):
py -3.12 scripts/setup.py

copy .env.example .env      # Windows; cp on macOS/Linux. Then fill in the values below.
```

### Configuration

Fill in `.env`. `.env.example` documents every variable.

| Variable | Where to get it |
|---|---|
| `LLM_PROVIDER` | `meterless` (default). Use `nim` only to switch to the NVIDIA NIM fallback |
| `METERLESS_API_KEY` | Meterless Nightshift runtime token: start Nightshift, then copy `<stateDir>/proxy-token` |
| `METERLESS_BASE_URL` | `http://127.0.0.1:8088/v1` (Nightshift's OpenAI-compatible runtime) |
| `METERLESS_MODEL` | `meterless/deep`, the Nemotron reasoning lane used for the demo (`meterless/auto` and `meterless/fast` also work) |
| `ZETARIS_JDBC_URL` | `jdbc:zetaris:lightning@localhost:10000` for the local Docker stack |
| `ZETARIS_JDBC_JAR` | `zetaris-platform/jdbc/ndp-jdbc-driver-*.jar` (full path) |
| `ZETARIS_USERNAME` / `ZETARIS_PASSWORD` | `ZETARIS_ADMIN_EMAIL` / `ZETARIS_ADMIN_PASSWORD` in `zetaris-platform/.env` |
| `ZETARIS_ORG_ID` | Zetaris web UI → Management → Organisation → numeric id (REST calls) |
| `ZETARIS_API_KEY` | Zetaris web UI → Management → API Tokens → create; used by the REST SQL endpoint and checked by `validate_stack.py` (the agent itself uses JDBC) |
| `CHANNELS_DB_PASSWORD` | any local password for the demo order DB (default `omni_demo_pw`) |
| `NVIDIA_NIM_API_KEY`, `NEMOTRON_MODEL` | optional, only with `LLM_PROVIDER=nim`: https://build.nvidia.com → Nemotron model → Get API Key |

### Run

```bash
.venv\Scripts\python.exe scripts/start_demo.py
```

This command:

1. builds the UI on first run (`npm ci` and `npm run build` in `demo/app`);
2. starts the channel order DB, unless one already answers on port 5433;
3. starts the source REST APIs on port 8901;
4. starts the demo UI.

Open **http://localhost:8902**. Choose **Reset demo** in the sidebar once to load the baseline.

To work on the UI with hot reload, keep the demo running, run `cd demo/app && npm install && npm run dev`,
and open http://localhost:5173. API calls are forwarded to port 8902.

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

`scripts/start_demo.py` runs steps 2 to 4 for you. Meterless Nightshift runs separately; start it before
you run the agent.

First-time Zetaris source registration writes to the instance, so run it once:

```bash
.venv\Scripts\python.exe scripts\register_demo_sources.py --execute                    # back-office sources
.venv\Scripts\python.exe scripts\register_demo_sources.py --file demo\register_channel_sources.sql --execute  # order sources
```

The Zetaris Unified Semantic Layer (optional) is set up by `demo/zetaris/usl_create.sql`. It is created
in its own namespace `lightning.metastore.omni_usl`:

```bash
.venv\Scripts\python.exe demo/zetaris/run_usl.py demo/zetaris/usl_create.sql
.venv\Scripts\python.exe demo/zetaris/run_usl.py demo/zetaris/usl_queries.sql
```

## Use it

The React app is served at `http://localhost:8902/`. It opens on a landing page and has a sidebar in two
groups and a search palette (Ctrl+K / ⌘K). **Theme** in the top bar (under **Menu** on phones) switches
between Auto, Light and Dark.

| Group | Section | URL | What it does |
|---|---|---|---|
| | Landing page | `/` | What the product does, with a scroll-driven story of one allocation cycle |
| OMS | Instructions | `/instructions` | A guided walk-through of the demo |
| OMS | Storefronts | `/storefronts` (also `/channels`) | Place orders on DTC, Amazon, Etsy and Walmart; each writes to that channel's own system (3 Postgres tables + 1 REST API) |
| IMS | Smart Allocation | `/smart-allocation` (also `/agent`) | How channels are ranked, every decision with its savings maths, **Approve** / **Deny** held changes, and memories recalled from H-MEM |
| IMS | Dashboard | `/dashboard` (also `/app`, `/ops`) | KPIs, what needs attention, stock health per SKU, charts, recent orders, the live **Agent run** trace |
| IMS | Orders | `/orders` | Every order in one queue: filter, search, fulfil, split (partial), cancel, bulk actions |
| IMS | Inventory | `/inventory`, `/inventory/<SKU>` | Stock per SKU, channel allocations, inbound shipments with projected arrival, days of cover |
| IMS | Data sources | `/sources` | The diagram of the separate sources feeding Zetaris, and the live federated SQL query |

The classic pages are still served at `/oms` and `/ims`, and also at `/classic/channels` and
`/classic/ops`.

**Run allocation cycle** (top right) runs the real agent. The Agent run card shows:

- the run status: queued, running, waiting for you, done or failed;
- elapsed time and each step;
- a lamp for every system the agent has read;
- **Run again** after a failure.

Other ways to run and check the agent:

- CLI: `.venv\Scripts\python.exe -m src.main "Run the allocation cycle for all four SKUs" --show-trace`
- Validate the stack: `.venv\Scripts\python.exe scripts\validate_stack.py` (exit 0 = no FAIL)
- Tests: `.venv\Scripts\python.exe -m pytest` → 67 passed
- H-MEM conformance: `npm --prefix engines/hmem run conformance` → 13/13 checks passed

## Design guarantees

- **Read-only Zetaris.** Every statement passes `ensure_read_only` (SELECT, SHOW, DESCRIBE, WITH or EXPLAIN only).
- **Deterministic math.** The LLM never computes numbers; `compute_allocation` does.
- **Guardrailed writes.**
  - Allocation caps.
  - Locked-SKU blocks.
  - Fallbacks for missing data.
  - Protection against zero or negative margin.
  - Human approval for pauses and for moves above 25%.
  - Moves with zero or negative projected savings are never applied.
- **Human judgement is remembered.** Approvals and denials become H-MEM memories with provenance,
  recalled per SKU.
- **Explainable output.**
  - One JSON record per SKU with reasoning, risks and `guardrails_checked`.
  - A summary of at most four sentences (see the system prompt in `src/prompts/omnismartalloc.py`).
  - The LLM provider and model that produced the record.

## Pre-existing components

These parts of the entry were not written from scratch in this repository during the build window:

- **H-MEM engine** (`engines/hmem/src/`). The same team wrote it during the event for its other entry,
  Ad Spend Autopilot, to the Meterless H-MEM spec. It is reused here; its retrieval features
  (`text.ts`), header comments and the CLI were adapted for inventory allocation.
- **H-MEM conformance runner and vectors** (`engines/hmem/conformance/`). Copied unmodified from
  meterless/meterless at commit `1742dec`, under Apache-2.0; the licence is next to them.
- **Chart.js v4.4.1** (`demo/web/vendor/chart.umd.js`, MIT) and the Satoshi font (Fontshare free licence).
- **Zetaris platform bundle and JDBC driver.** From the hackathon materials, used locally and not
  committed (`zetaris-platform/`, `*.jar` are gitignored).
- **Data.** All demo data is synthetic and was created in this repository during the event. Git history
  shows that `demo/data/` was first committed on 2026-10-25 (`404aec4`, "Add OmniSmartAlloc agent,
  demo UI, and per-channel order sources"). `demo/baseline/` was added on 2026-10-25 (`6ae168c`,
  "Baseline data") and updated on 2026-10-26 (`df38a01`, `2c342ff`). The repository's first commit is
  the scaffold on 2026-10-24 (`6520509`). No dataset predates the repository.

Third-party licences are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). OmniSmartAlloc is
MIT-licensed ([LICENSE](LICENSE)).
