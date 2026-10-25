# AGENTS.md

Track 1 (Solving Fragmented Intelligence): Nemotron ReAct agent that discovers and queries across Zetaris-federated sources.

- Python: use `py -3.12` on this Windows machine (`python` is the Store stub). Venv: `.venv/Scripts/python.exe`.
- Setup (idempotent): `py -3.12 scripts/setup.py`
- Tests (offline, fakes in `tests/conftest.py`): `.venv/Scripts/python.exe -m pytest`
- Validate stack: `.venv/Scripts/python.exe scripts/validate_stack.py` (`--skip-network` for offline checks). Exit 1 on any FAIL.
- Run agent: `.venv/Scripts/python.exe -m src.main "question" --show-trace`
- Secrets live in `.env` / `.env.local` (gitignored); process env takes precedence over `.env`.
- Layout: `src/agent` (ReAct loop), `src/tools` (registry + discovery tools), `src/data_connectors` (Zetaris JDBC + read-only guard), `src/prompts`, `src/llm.py` (NIM/Meterless), `src/config.py`.
- All SQL goes through `ensure_read_only` (single SELECT/SHOW/DESCRIBE/WITH/EXPLAIN statement).
- Use case: OmniSmartAlloc (multi-channel inventory allocation). Spec: `src/prompts/omnismartalloc.py` (from the user's "Agent System Prompt" doc). Deterministic math in `src/allocation/engine.py`; tools in `src/tools/allocation_tools.py`; outputs in `demo/outbox/` (gitignored).
- Demo data: `demo/data/*.json` served by `python demo/mock_apis.py 8901`; registered in Zetaris by `scripts/register_demo_sources.py --execute` (WRITES - needs user approval; dry run by default).
- Channel orders: DTC/Etsy/Walmart in Postgres container `omni-channels-db` (`docker compose -f demo/docker-compose.channels.yml up -d`, host port 5433), Amazon in `demo/data/amazon_orders.json` served at `/api/amazon/orders`. Store layer: `demo/order_stores.py`. Zetaris: JDBC datasource `CHANNEL_DB` + REST `AMAZON_API` (`demo/register_channel_sources.sql`).
- Demo UI: `python demo/server.py` -> http://localhost:8902 (`/channels`, `/ops`); needs mock APIs on 8901 and the channel DB.
- Zetaris local stack: `zetaris-platform/` (gitignored) at repo root; manage with `docker compose` from that dir.
- Zetaris docs: https://zetaris.github.io/getting-started/ (JDBC driver class `com.zetaris.lightning.jdbc.LightningDriver`, REST base `http://localhost:8888/api/v1.0`).
