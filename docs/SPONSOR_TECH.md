# Sponsor technology in OmniSmartAlloc

OmniSmartAlloc is an inventory-allocation agent for a seller on four channels (DTC, Amazon, Etsy,
Walmart). It needs facts from six systems that were never built to work together. This page describes
what each sponsor technology does in the product and where to find it in the code. All data is synthetic.

| Sponsor | What it does here | Code | Proof |
|---|---|---|---|
| **Zetaris** | Federates the six sources into one SQL surface (`CHANNEL_DB.*`, `omnismart.*`), plus a Unified Semantic Layer with DQ rules | `src/data_connectors/zetaris_jdbc.py`, `src/data_connectors/readonly.py`, `src/allocation/snapshot.py`, `demo/register_*.sql`, `demo/zetaris/` | `docs/ZETARIS_USL.md`, `demo/zetaris/results/` |
| **Meterless Nightshift** | Primary model provider: the agent's chat completions go to Nightshift's OpenAI-compatible runtime | `src/llm.py`, `.env.example` | `tests/test_llm_provider.py`; `scripts/validate_stack.py` pings the runtime |
| **Meterless engine: H-MEM** | Long-term decision memory: human approvals and denials are stored as memories and recalled per SKU on the next run | `engines/hmem/`, `src/memory/hmem.py`, `src/allocation/agent_log.py`, `src/tools/allocation_tools.py` | `npm --prefix engines/hmem run conformance` (13/13), `tests/test_hmem_memory.py` |
| **NVIDIA Nemotron** | Plans the ReAct cycle, chooses and calls tools, and writes the reasoning and summary for each SKU | `src/agent/react.py`, `src/prompts/omnismartalloc.py` | `tests/test_react_smoke.py`, `docs/SAMPLES.md` |

## Zetaris

**Sources.** One JDBC datasource and five REST sources are registered in Zetaris Lightning:

| Zetaris name | Kind | Backing system | Holds |
|---|---|---|---|
| `CHANNEL_DB` | JDBC (`CREATE DATASOURCE`, Postgres) | `omni-channels-db` container | `dtc_orders`, `etsy_orders`, `walmart_orders` |
| `AMAZON_API` | REST (`CREATE LIGHTNING REST TABLE`) | `demo/mock_apis.py` `/api/amazon/orders` | Amazon seller orders |
| `WMS` | REST | `demo/mock_apis.py` | on-hand, committed, inbound POs |
| `SUPPLIER_PORTAL` | REST | `demo/mock_apis.py` | supplier on-time rate, lane delays |
| `CHANNEL_ANALYTICS` | REST | `demo/mock_apis.py` | unit margin, velocity, demand confidence per SKU and channel |
| `RULES_ENGINE` | REST | `demo/mock_apis.py` | locks, floors, promotions |

Registration scripts are `demo/register_sources.sql` and `demo/register_channel_sources.sql`, run by
`scripts/register_demo_sources.py --execute`.

**Schemastore views.** The REST responses are flattened into the `omnismart` schemastore container
(`omnismart.wms_inventory`, `wms_inbound`, `supplier_reliability`, `channel_economics`, `sku_rules`,
`amazon_orders`). The agent and the snapshot loader read these views and the `CHANNEL_DB.*` tables.

**Read-only guard.** Every statement the agent sends goes through `ensure_read_only` in
`src/data_connectors/readonly.py`, which allows a single SELECT, SHOW, DESCRIBE, WITH or EXPLAIN
statement only. The agent cannot change the sources.

**Federated query.** One Lightning SQL statement unions the three Postgres tables with the Amazon REST
table to give per-channel demand. The Data sources page runs it live (`/api/federated` in
`demo/server.py`), and `compute_allocation` builds each SKU's snapshot from the federated views
(`src/allocation/snapshot.py`).

**Unified Semantic Layer.** `demo/zetaris/usl_create.sql` defines the USL `omnialloc` in namespace
`lightning.metastore.omni_usl`. It has six tables (`sku`, `supplier`, `inventory`, `inbound_po`,
`channel_economics`, `channel_order`) with keys, activations over the federated sources, and DQ rules
such as `committed_within_on_hand`. The full walkthrough, with captured results, is in
[ZETARIS_USL.md](ZETARIS_USL.md).

## Meterless Nightshift: the primary AI provider

`src/llm.py` selects Meterless Nightshift unless `LLM_PROVIDER=nim` is set explicitly. It uses:

- endpoint `METERLESS_BASE_URL` (default `http://127.0.0.1:8088/v1`), Nightshift's OpenAI-compatible runtime;
- token `METERLESS_API_KEY`, which Nightshift writes to `<stateDir>/proxy-token`;
- lane `METERLESS_MODEL` (default `meterless/deep`), which Nightshift routes to an NVIDIA Nemotron model;
- a `meterless-app` header for usage attribution and a per-request `meterless-scope: user` header.

Each decision record written by the agent carries `llm_provider` and `llm_model`, so you can see which
provider produced it. NVIDIA NIM is kept only as an optional fallback (`LLM_PROVIDER=nim`).

## Meterless engine: H-MEM decision memory

**What it does here.** A reviewer approves or denies a held allocation proposal (for example a channel
pause, or a move above the 25% change limit) on the Smart Allocation page. That decision becomes an
H-MEM memory with:

- the SKU, the channel moves (for example `Amazon 3→19, Walmart 16→10`) and the decision;
- the reviewer's reason and the reviewer's name;
- provenance `approval:<id>`, origin `user_correction`;
- namespace `sku:<SKU>`.

The next time `compute_allocation` runs for that SKU, it recalls the SKU's memories, ranked by H-MEM's
hybrid score. Recalled memories are:

- added to the record's reasoning (`Recalled from memory (mem-3, approval 1bf4118b, …)`);
- returned to the model as `recalled_memories`; the system prompt tells Nemotron to treat them as the
  reviewers' standing preferences and cite them;
- stored on the next proposal and shown on its Smart Allocation card under **Recalled from memory**.

When a proposal built on recalled memories is approved, those memories get H-MEM `helpful` feedback
(+0.05 confidence, recorded in the append-only ledger). If Node is unavailable, the agent logs a
warning and falls back to the approvals log (`agent_log.denied()`), so allocation never stops.

**Implementation.** `engines/hmem/src/hmem.ts` implements the
[Meterless H-MEM spec](https://github.com/meterless/meterless/tree/main/engines/hmem). It provides:

- tiered layers and provenance on every record;
- hybrid ranking and the exact feedback deltas;
- an append-only trust ledger;
- a preview-first sleep cycle with guardrails;
- conflict detection that supersedes and never deletes;
- dreaming proposals that need approval.

It runs on plain Node 22.18+ with no npm dependencies. `engines/hmem/src/cli.ts` serves add, query,
feedback and all requests as JSON over stdin/stdout, and `src/memory/hmem.py` calls it. State lives
in `demo/outbox/memory/state.json` and `ledger.jsonl`.

**Tests that show it works.**

```bash
npm --prefix engines/hmem run conformance          # official Meterless runner + vectors: 13/13 checks passed
.venv/Scripts/python.exe -m pytest tests/test_hmem_memory.py
```

`tests/test_hmem_memory.py` runs the real engine and covers six cases:

- deny → memory written with provenance → recalled on the next `compute_allocation` → present in the
  tool result and the reasoning;
- recall is scoped to the SKU;
- approve → memory, and the recalled memories are marked helpful (exact +0.05);
- engine failure → fallback to the approvals log;
- the engine can be switched off;
- the official conformance suite passes.

## NVIDIA Nemotron

Nemotron, served through Meterless Nightshift, drives the ReAct loop in `src/agent/react.py`. It:

- reads the system prompt in `src/prompts/omnismartalloc.py`;
- discovers sources (`list_sources`, `list_tables`, `describe_table`) and inspects demand with `run_query`;
- calls `compute_allocation` for each SKU and writes with `set_channel_allocation`;
- raises alerts with `create_alert` and records its reasoning and summary with `log_decision`.

Nemotron does not do the arithmetic: the deterministic engine in `src/allocation/engine.py` computes
sellable units, inbound credit, state and the margin-ranked allocation. Nemotron decides what to look
at, in what order, and how to explain it.

## What is unique

- **Human judgement persists.** A denial is not a one-off log line. It becomes a ranked, auditable H-MEM
  memory with provenance, recalled per SKU and shown to both the model and the reviewer.
- **Guardrails are in code, not in the prompt.** These are enforced in `set_channel_allocation`:
  - the sellable cap;
  - the 25% change limit;
  - pauses need approval;
  - a move with zero or negative projected savings is never applied.
- **Federation instead of ETL.** Postgres orders and REST order APIs are joined in one Zetaris query.
  The USL adds keys and DQ rules over the same live sources, without copying data.
