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
- Zetaris local stack: `zetaris-platform/` (gitignored) at repo root; manage with `docker compose` from that dir.
- Zetaris docs: https://zetaris.github.io/getting-started/ (JDBC driver class `com.zetaris.lightning.jdbc.LightningDriver`, REST base `http://localhost:8888/api/v1.0`).
