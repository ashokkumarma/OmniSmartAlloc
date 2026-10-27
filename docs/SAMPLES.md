# Sample inputs and outputs

These are real runs, not mock-ups. The raw records are copied unchanged into `docs/samples/`. Live output
normally goes to the gitignored `demo/outbox/`. All data is synthetic.

| # | Input | Output | Raw records |
|---|---|---|---|
| 1 | Scenario A: a 30-unit Amazon order for MUG-001 is fulfilled | **Needs approval**, approved by a human; +$171 projected | `docs/samples/approvals.jsonl` (`1bf4118b`), `docs/samples/allocations.jsonl` |
| 2 | CLI: "Run the allocation cycle for all four SKUs" | 2 auto-applied, 1 held for approval, 1 auto-declined, 3 alerts | `docs/samples/live-2026-10-27/cli_full_cycle.txt` and `*.jsonl` |
| 3 | A reviewer denies the MUG-001 proposal with a reason, then the agent runs again | H-MEM memory `mem-1` is recalled; the agent cites it in its reasoning and summary; the card shows it | `docs/samples/live-2026-10-27/cli_mug001_after_denial.txt`, `hmem_state.json`, `hmem_ledger.jsonl` |
| 4 | Agent cycle after LAMP-002 orders on DTC | **Needs approval** because DTC would move 28% (over the 25% limit); +$32 projected | `docs/samples/approvals.jsonl` (`0ecf9588`) |

Runs 2 and 3 were made on 2026-10-27 from 13:46 to 13:50 UTC with Meterless Nightshift as the provider
(`METERLESS_MODEL=meterless/deep`). Every decision record from those runs carries
`"llm_provider": "meterless", "llm_model": "meterless/deep"`. Runs 1 and 4 come from the UI demo on
2026-10-27 between 00:11 and 00:48 UTC; their records predate the provider field.

---

## 1. Scenario A: MUG-001, 30-unit Amazon order → Needs approval

**Input** (the steps on the in-app Instructions page):

1. In Storefronts, choose Amazon, set MUG-001 to 30 and click Place order.
2. In Orders, click Fulfill all.
3. The agent runs automatically.

**What the agent saw.** Before the order, Amazon held 33 units. The fulfilled order drew Amazon's own
stock down to 3:

- sellable = 100 on hand − 30 committed = **70**;
- demand ≈ 30 units/day, so about **2.3 days of cover**;
- PO-9001 (200 units) arrives in ~9 days, after the stock-out, so it gets no supply credit;
- state is **Tight**.

**Output** (approval `1bf4118b`, 2026-10-27T00:11:47Z):

| Channel | Cap before | Cap after |
|---|---|---|
| DTC | 44 | 36 |
| Amazon | 3 | 19 |
| Etsy | 7 | 5 |
| Walmart | 16 | 10 |

- **Needs approval.** These moves exceed the 25% per-run limit: Walmart 38%, Etsy 29%, Amazon 533%.
  `set_channel_allocation` staged the change and wrote nothing.
- **Projected savings: +$171.**
  - With the change: Amazon +16 units × $16 = $256.
  - Without the change: units kept on DTC/Etsy/Walmart would earn $85, capped at each channel's demand
    over 2.3 days.
- **Why (from the card):** "DTC sells ~6/day — it needs only ~14 units over the next 2.3 days, so
  cutting its limit 44 → 36 gives up no real sales." "Amazon sells ~14/day — the 16 units moved here
  enable up to ~16 more sales."
- **A human approved it at 00:25:43Z.** The allocation record carries `"note": "human-approved"` and
  `"approval_id": "1bf4118b"`.

The agent also raised an alert: "Tight supply state: projected gap of about 7 days (~200 units)". The
recommended action was "Expedite inbound PO", with a deadline of "within 2 days".

## 2. Full allocation cycle from the CLI (Meterless Nightshift → Nemotron)

**Input:**

```bash
.venv\Scripts\python.exe -m src.main "Run the allocation cycle for all four SKUs" --show-trace
```

**Trace** (19 tool calls, from `cli_full_cycle.txt`):

1. `list_sources` and `list_tables` on WMS and CHANNEL_DB (discovery in Zetaris).
2. `run_query`: `SELECT DISTINCT sku FROM omnismart.wms_inventory` returns 4 SKUs.
3. `compute_allocation` for each SKU.
4. `set_channel_allocation` for each SKU.
5. `create_alert` for the 3 Tight SKUs.
6. `log_decision` for each SKU.

Sources touched: CHANNEL_ANALYTICS, CHANNEL_DB, RULES_ENGINE, SUPPLIER_PORTAL, WMS, omnismart.

**Output:**

| SKU | State | Days of cover | Allocation (DTC / Amazon / Etsy / Walmart) | Write | Projected |
|---|---|---|---|---|---|
| LOCK-004 | Abundant | 73.0 | 25 / 50 / 0 / 0 (shared pool) | **Auto-applied** | +$220 |
| LAMP-002 | Tight | 3.4 | 18 / 2 / 3 / 1 | **Auto-applied** (state moved Abundant → Tight, so the per-run 25% step limit does not apply) | +$19 |
| MUG-001 | Tight | 2.3 | 36 / 19 / 5 / 10 | **Needs approval** (`34037f77`): Amazon +533%, Etsy −29% | +$221 |
| RUG-003 | Tight | 6.0 | 22 / 6 / 1 / 1 | **Auto-declined**: no projected savings, so nothing is redistributed | — |

Nemotron's summary (excerpt): "LOCK-004 is in abundant supply (73 days of cover) with 75 sellable
units allocated DTC 25 / Amazon 50, and the write was applied. MUG-001, LAMP-002, and RUG-003 are all
tight with days of cover of 2.3, 3.4, and 6.0 respectively; …"

## 3. H-MEM: a denial is remembered on the next run

**Input:**

1. A reviewer denied MUG-001 proposal `34037f77` (from run 2) with the reason "Keep Walmart at 16: we
   have a Walmart rollback promo running this week". It was recorded with `agent_log.deny`, the
   function behind the Deny button (`POST /api/approvals/<id>/deny`), with `reviewer="Francis (ops)"`.
2. The agent then ran `-m src.main "Run the allocation cycle for MUG-001"`.

**Memory written** (`hmem_state.json`):

| Field | Value |
|---|---|
| id | `mem-1` |
| namespace | `sku:MUG-001` |
| type / layer | `preference` / `working` |
| confidence | 0.85 |
| provenance | `{"origin": "user_correction", "refs": ["approval:34037f77"]}` |

Its content: "Francis (ops) denied the MUG-001 allocation proposal 34037f77 (Amazon 3→19, DTC 44→36,
Etsy 7→5, Walmart 11→10). Reason: Keep Walmart at 16: we have a Walmart rollback promo running this
week."

The ledger (`hmem_ledger.jsonl`) records the `create` and the later `read`.

**Output of the next run** (`cli_mug001_after_denial.txt`):

- `compute_allocation` recalled the memory and added it to the reasoning: "Recalled from memory (mem-1,
  approval 34037f77, relevance 0.52): Francis (ops) denied the MUG-001 allocation proposal …"
- Nemotron passed it on in the write reason: "Applying computed allocation respecting recent denial
  mem-1 (34037f77) to keep Walmart at 16 due to rollback promo; allocation sets Walmart at 10 which is
  below the protected level."
- The summary says: "A human previously denied a similar proposal (mem-1, approval 34037f77) asking to
  keep Walmart at 16 due to a rollback promo, so that preference was noted."
- The new proposal `a3bf31ec` stores `recalled_memories: [mem-1]`, so its Smart Allocation card shows
  the denial under **Recalled from memory**.
- If the reviewer approves it, `mem-1` gets H-MEM `helpful` feedback (+0.05).

**What this does not do (yet).** The memory shapes the reasoning, the summary and what the reviewer
sees, but it does not change the numbers. The deterministic engine has no "keep Walmart at 16" floor,
so the agent re-proposed Walmart 10. The proposal is still held for approval, and the reviewer sees
their own earlier reason on the card. Turning recalled preferences into engine constraints (for example
a per-channel floor in `RULES_ENGINE`) is the natural next step.

## 4. LAMP-002: the 25% guardrail holds a profitable move

**Input:** DTC orders for LAMP-002 were placed and fulfilled in the UI, then the agent cycle ran
(2026-10-27T00:48:10Z).

**Output** (approval `0ecf9588`):

| Channel | Before | After |
|---|---|---|
| DTC | 18 | 23 |
| Amazon | 19 | 18 |
| Etsy | 9 | 7 |
| Walmart | 9 | 7 |

- **Needs approval.** "DTC would move 5 of its 18 units (28% — over the 25% limit): human approval
  needed."
- **Projected savings: +$32.** That is DTC +5 × $14 = $70, minus $38 of demand-capped margin that
  Etsy, Walmart and Amazon would give up.
- **Why:** "DTC is selling 3.4 units/day, vs its usual 2.1/day. Units are moved here so the
  faster-selling channel does not run out." "Amazon is only selling 1.7/day (59% of its usual pace)."
