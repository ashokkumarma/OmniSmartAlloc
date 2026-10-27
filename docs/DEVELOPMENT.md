# Development notes

Track 1 (Solving Fragmented Intelligence): a Nemotron ReAct agent that discovers and queries
Zetaris-federated sources and allocates inventory across sales channels.

## Environment

- Python 3.11+ (on Windows use `py -3.12`; `python` may be the Store stub). Venv: `.venv/Scripts/python.exe`.
- Node 22.18+ on PATH for the H-MEM engine (`engines/hmem`, no npm install needed) and Node 20+ with npm to build `demo/app`.
- Setup (idempotent): `py -3.12 scripts/setup.py`
- Secrets live in `.env` / `.env.local` (gitignored); the process environment takes precedence over `.env`.

## Everyday commands

| What | Command |
|---|---|
| Offline tests (fakes in `tests/conftest.py`; H-MEM tests use Node) | `.venv/Scripts/python.exe -m pytest` |
| H-MEM official conformance (expects 13/13) | `npm --prefix engines/hmem run conformance` |
| Validate the stack (`--skip-network` for offline checks; exit 1 on any FAIL) | `.venv/Scripts/python.exe scripts/validate_stack.py` |
| Run the agent from the CLI | `.venv/Scripts/python.exe -m src.main "Run the allocation cycle for all four SKUs" --show-trace` |
| Build the React UI | `cd demo/app && npm ci && npm run build` |
| Zetaris USL scripts | `.venv/Scripts/python.exe demo/zetaris/run_usl.py demo/zetaris/usl_queries.sql` |

## Layout

- `src/agent` ReAct loop; `src/tools` registry, discovery and allocation tools; `src/data_connectors`
  Zetaris JDBC connector and the read-only guard; `src/prompts`; `src/llm.py` (Meterless Nightshift
  primary, NVIDIA NIM fallback); `src/memory` (H-MEM decision memory); `src/config.py`.
- All SQL goes through `ensure_read_only` (a single SELECT/SHOW/DESCRIBE/WITH/EXPLAIN statement).
- Allocation spec: `src/prompts/omnismartalloc.py`. Deterministic math: `src/allocation/engine.py`.
  Tools: `src/tools/allocation_tools.py`. Outputs: `demo/outbox/` (gitignored).
- Demo data: `demo/data/*.json`, served by `python demo/mock_apis.py 8901`; registered in Zetaris by
  `scripts/register_demo_sources.py --execute` (writes to the Zetaris instance; dry run by default).
- Channel orders: DTC/Etsy/Walmart in the Postgres container `omni-channels-db`
  (`docker compose -f demo/docker-compose.channels.yml up -d`, host port 5433); Amazon orders in
  `demo/data/amazon_orders.json`, served at `/api/amazon/orders`. Store layer: `demo/order_stores.py`.
  Zetaris: JDBC datasource `CHANNEL_DB` + REST `AMAZON_API` (`demo/register_channel_sources.sql`).
- Demo UI: `python demo/server.py` -> http://localhost:8902; needs the mock APIs on 8901 and the channel DB.
- Zetaris local stack: `zetaris-platform/` (gitignored) at the repo root; manage it with `docker compose` from that folder.
- Zetaris docs: https://zetaris.github.io/getting-started/ (JDBC driver class
  `com.zetaris.lightning.jdbc.LightningDriver`, REST base `http://localhost:8888/api/v1.0`).
