# OmniSmartAlloc on the Zetaris Unified Semantic Layer

OmniSmartAlloc decides how a retailer's limited stock is split across sales channels: DTC, Amazon, Etsy and Walmart. To make that decision it needs data from six systems that do not talk to each other. This document covers how those six systems were explored in Zetaris, modelled as one Unified Semantic Layer (USL) with data-quality rules, and compared with a hand-coded integration.

Everything below was run live against a local Zetaris Lightning instance over JDBC on 27 October 2026. Every result quoted is copied from the captured output in `demo/zetaris/results/`. **All data is synthetic.**

| Artifact | Purpose |
|---|---|
| `demo/zetaris/explore_*.sql` (6 files) | Exploratory queries, 3 per source |
| `demo/zetaris/usl_create.sql` | Namespace, 6-table USL DDL, activations, DQ rules, RUN DQ |
| `demo/zetaris/usl_queries.sql` | Queries that read only the active USL |
| `demo/zetaris/run_usl.py` | Runner: splits statements, skips comments, keeps a multi-table `COMPILE USL` whole, records results |
| `demo/zetaris/results/*.md`, `*.json` | Captured results of every statement |
| `demo/zetaris/handcoded_equivalent.py` | The same outputs computed directly from Postgres and the REST APIs, without Zetaris |

To reproduce, run these from the repo root with the project virtualenv. Zetaris, the channel Postgres and `demo/mock_apis.py` must already be running:

```bash
python demo/zetaris/run_usl.py                   # all 8 SQL files, in order; results -> demo/zetaris/results/
python demo/zetaris/handcoded_equivalent.py      # hand-coded equivalent + agreement check against the USL results
```

---

## 1a. Sources and why each one is needed

Each source is a separate system in the demo, with its own owner, format and update cadence. Zetaris federates them: the data is never copied.

| Zetaris source | Type | Tables | What the allocator needs from it |
|---|---|---|---|
| `CHANNEL_DB` | Postgres over JDBC (`CREATE DATASOURCE`) | `dtc_orders`, `etsy_orders`, `walmart_orders` | Order history and open demand for the three channels the retailer runs itself |
| `AMAZON_API` | REST (`CREATE LIGHTNING REST TABLE`) | `orders_raw` | Amazon orders, which live only behind the seller API |
| `WMS` | REST | `inventory_raw`, `inbound_raw` | On-hand and committed stock, plus inbound purchase-order lines and their ETAs |
| `SUPPLIER_PORTAL` | REST | `reliability_raw` | Supplier on-time rate and typical delay, used to discount inbound stock |
| `CHANNEL_ANALYTICS` | REST | `economics_raw` | Per-SKU, per-channel unit margin, 7/30/90-day velocity and demand confidence |
| `RULES_ENGINE` | REST | `rules_raw` | Per-SKU locks, manual overrides, clearance flags and promotion multipliers |

These six sources cover everything the allocation formula needs: stock, inbound supply and its risk, channel economics, demand, and business rules. Leave any one out and the allocation is either wrong or unsafe. For example, without `RULES_ENGINE` a locked SKU would still get allocated, and without `SUPPLIER_PORTAL` every purchase order would be assumed to arrive on time. Mixing JDBC with REST is deliberate. Real retailers run order databases next to SaaS APIs, and the mix is where federation earns its keep.

The sources were registered earlier by `demo/register_sources.sql` and `demo/register_channel_sources.sql`, which also created the `omnismart.*` SchemaStore views that the live agent reads today. The USL work below reads the same raw sources and does not change any of them.

## 1b. Exploratory queries and results

There are three queries per source. The full SQL is in `demo/zetaris/explore_*.sql`, and every result row is in `demo/zetaris/results/explore_*.md`. All 18 statements succeeded, each in 0.04 to 1.14 s.

**CHANNEL_DB (Postgres).** `SHOW DATASOURCE TABLES` lists the three order tables. `DESCRIBE DATASOURCE TABLE` shows that Postgres keeps its own types (`qty integer`, `id string PK`). An aggregate across all three tables gives:

| channel | status | orders | units | open_units |
|---|---|---|---|---|
| DTC | fulfilled | 346 | 481 | 0 |
| DTC | open | 3 | 9 | 9 |
| DTC | cancelled | 15 | 26 | 26 |
| Etsy | fulfilled | 142 | 192 | 0 |
| Walmart | fulfilled | 198 | 294 | 0 |
| Walmart | open | 2 | 2 | 2 |

**AMAZON_API (REST).** `DESCRIBE AMAZON_API.orders_raw` shows the schema Zetaris fixed when the table was registered:
`array<struct<fulfilled_qty:bigint,id:string,partial_shipments:array<string>,qty:bigint,sku:string,status:string,ts:string>>`.
Note `partial_shipments:array<string>`, which matters in section 2c. Flattened with `LATERAL VIEW explode(orders)`, the table returns, for example, LAMP-002 with 262 fulfilled orders (281 units) and MUG-001 with 53 fulfilled and 7 cancelled.

**WMS (REST).** Stock is LAMP-002 24, LOCK-004 75, MUG-001 70 and RUG-003 30 on hand, with 0 committed on every SKU. Inbound has 6 PO lines: LAMP-002 has 400 units in transit (soonest ETA 4 days), and RUG-003 has 200 in transit plus 200 planned at 40 days.

**SUPPLIER_PORTAL (REST), plus a cross-source join with WMS.** The suppliers are BRIGHT (0.9 on time, 1-day delay), ACME-EAST (0.8, 4 days) and KEYCO (0.6, 10 days). Joining with WMS inbound shows how many units are likely to arrive late: ACME-EAST 160 of 800, KEYCO 80 of 200, BRIGHT 20 of 200.

**CHANNEL_ANALYTICS (REST).** There are 14 SKU x channel rows. Ranked by margin x 30-day velocity x confidence, the best channel is DTC for LAMP-002 (29.4) and RUG-003 (201.6), and Amazon for MUG-001 (224.0) and LOCK-004 (40.0).

**RULES_ENGINE (REST).** All 4 SKUs are currently unlocked, with no clearance and a promotion multiplier of 1.0. The source is still explored, because a single lock here zeroes a SKU's allocation.

**One failure during exploration.** The first version of the SUPPLIER_PORTAL x WMS join put `LATERAL VIEW explode(...)` directly on the left-hand table of a `JOIN`. The Lightning parser rejected it with this error:

```text
com.zetaris.lightning.sql.parser.ddl.LightningDdlParseException:
mismatched input 's' expecting 'METADATA'(line 1, pos 7)
```

Moving each side's flattening into its own subquery fixed it. That version is the one in the file.

## 1c. The USL: DDL, activation, active queries, and data quality

### Model

The USL is `omnialloc` in namespace `lightning.metastore.omni_usl`, with six tables. Every table is keyed by SKU or by a composite of SKU and channel, PO or order. Foreign keys point back to `sku` and `supplier`, so Zetaris draws the ERD and generates referential DQ rules automatically.

```sql
COMPILE USL IF NOT EXISTS omnialloc DEPLOY NAMESPACE lightning.metastore.omni_usl DDL
CREATE TABLE sku (sku varchar(64) NOT NULL PRIMARY KEY, locked boolean, manual_override boolean,
                  clearance boolean, promo_multiplier double);
CREATE TABLE supplier (supplier varchar(64) NOT NULL PRIMARY KEY, on_time_rate double, typical_delay_days bigint);
CREATE TABLE inventory (sku varchar(64) NOT NULL PRIMARY KEY FOREIGN KEY REFERENCES sku(sku),
                        on_hand bigint, committed bigint, unputaway bigint, age_hours double);
CREATE TABLE inbound_po (po_line varchar(140) NOT NULL PRIMARY KEY, po varchar(64),
                         sku varchar(64) FOREIGN KEY REFERENCES sku(sku), qty bigint, eta_days bigint, status varchar(32),
                         supplier varchar(64) FOREIGN KEY REFERENCES supplier(supplier));
CREATE TABLE channel_economics (sku_channel varchar(140) NOT NULL PRIMARY KEY,
                                sku varchar(64) FOREIGN KEY REFERENCES sku(sku), channel varchar(32),
                                unit_margin double, demand_confidence double, v7 double, v30 double, v90 double,
                                trend double, floor_units bigint, margin_age_hours bigint);
CREATE TABLE channel_order (order_key varchar(140) NOT NULL PRIMARY KEY, channel varchar(32), order_id varchar(64),
                            sku varchar(64) FOREIGN KEY REFERENCES sku(sku), ts varchar(40),
                            qty bigint, fulfilled_qty bigint, status varchar(32))
```

(The file has one column per line. The statement is sent as **one** JDBC call, because `run_usl.py` merges the `CREATE TABLE` chunks back into the `COMPILE` statement.)

Each table is then activated over its federated source. The most interesting activation is `channel_order`, which is **one query over two kinds of source**: three Postgres tables over JDBC plus the Amazon REST API.

```sql
ACTIVATE USL TABLE lightning.metastore.omni_usl.omnialloc.channel_order AS
SELECT COALESCE(concat('DTC:', id), '') AS order_key, 'DTC' AS channel, id AS order_id, sku, ts,
       CAST(qty AS bigint) AS qty, CAST(fulfilled_qty AS bigint) AS fulfilled_qty, status
FROM CHANNEL_DB.dtc_orders
UNION ALL SELECT ... FROM CHANNEL_DB.etsy_orders
UNION ALL SELECT ... FROM CHANNEL_DB.walmart_orders
UNION ALL
SELECT COALESCE(concat('Amazon:', o.id), ''), 'Amazon', o.id, o.sku, o.ts, o.qty, o.fulfilled_qty, o.status
FROM AMAZON_API.orders_raw LATERAL VIEW explode(orders) AS o
```

Design choices:

- **Types.** REST integers arrive as `bigint` and decimals as `double`, so the DDL declares those types. ACTIVATE does not allow a query column to be narrowed to a smaller declared type.
- **Keys.** Composite keys are built as strings, for example `concat(sku,'|',channel)`, and wrapped in `COALESCE` to satisfy `NOT NULL`.
- **No self-joins.** No activation or query reads the same source table twice, because a known Lightning issue returns the first read's rows for the second read of the same table.

**Execution (`results/usl_create.md`): all 20 statements succeeded on the first live run and on a full re-run.** The namespace create, compile, all 6 activations, the description update, 3 `REGISTER DQ` calls, `LIST DQ USL`, 4 `RUN DQ` calls, `SHOW DQ INVALID RECORD` and `SHOW NAMESPACES OR TABLES` each took 0.03 to 2.56 s.

### Queries proving the USL is active (`usl_queries.sql`, 4/4 succeeded)

These queries name only `lightning.metastore.omni_usl.omnialloc.*` tables. Zetaris resolves each one to its live source.

**Row counts per USL table:** sku 4, supplier 3, inventory 4, inbound_po 6, channel_economics 14, channel_order 1085 (DTC + Etsy + Walmart from Postgres plus Amazon from REST).

**Sellable units per SKU.** Each SKU's sellable units are free stock plus inbound units expected within 7 days. Inbound is weighted by the supplier's on-time rate, and a SKU drops to 0 if it is locked. The query joins four USL tables (inventory, sku, inbound_po, supplier) across three sources:

| sku | on_hand | committed | free_now | inbound_units | expected_inbound_7d | sellable_7d | blocked |
|---|---|---|---|---|---|---|---|
| LAMP-002 | 24 | 0 | 24 | 400 | 340.0 | 364.0 | False |
| LOCK-004 | 75 | 0 | 75 | 200 | 160.0 | 235.0 | False |
| MUG-001 | 70 | 0 | 70 | 200 | 160.0 | 230.0 | False |
| RUG-003 | 30 | 0 | 30 | 400 | 160.0 | 190.0 | False |

**Channel scores with open demand from all four channels.** Score = margin x v30 x confidence x promo. These are the top rows for two SKUs:

| sku | channel | unit_margin | v30 | demand_confidence | channel_score | orders_seen | open_units | rank |
|---|---|---|---|---|---|---|---|---|
| MUG-001 | Amazon | 16.0 | 14.0 | 1.0 | 224.0 | 60 | 16 | 1 |
| MUG-001 | DTC | 24.0 | 6.0 | 0.9 | 129.6 | 98 | 20 | 2 |
| MUG-001 | Walmart | 10.0 | 7.0 | 0.9 | 63.0 | 112 | 22 | 3 |
| MUG-001 | Etsy | 13.0 | 3.0 | 0.8 | 31.2 | 44 | 4 | 4 |
| RUG-003 | DTC | 112.0 | 2.0 | 0.9 | 201.6 | 32 | 0 | 1 |
| RUG-003 | Amazon | 75.0 | 2.0 | 1.0 | 150.0 | 18 | 6 | 2 |

**Proposed split of free stock in proportion to channel score.** One example from the output: MUG-001's 70 free units split as Amazon 35, DTC 20, Walmart 9 and Etsy 4. The full table for all 14 rows is in `results/usl_queries.md`.

### Data-quality rules and RUN DQ results

The headline rule is on `inventory`:

```sql
REGISTER DQ committed_within_on_hand TABLE lightning.metastore.omni_usl.omnialloc.inventory AS
on_hand IS NOT NULL AND committed IS NOT NULL AND committed >= 0 AND committed <= on_hand
```

It matters because the allocator gives away `on_hand - committed`. If committed ever exceeds on-hand, or is missing, the allocator could promise stock that does not exist. That oversell is exactly what OmniSmartAlloc is meant to prevent. Two supporting rules were also registered:

- `margin_and_confidence_sane` on `channel_economics`: `unit_margin >= 0 AND demand_confidence >= 0 AND demand_confidence <= 1`
- `fulfilled_within_ordered` on `channel_order`: `fulfilled_qty >= 0 AND fulfilled_qty <= qty`

`LIST DQ USL` returned 14 constraints and rules: 6 primary keys, 5 FK-generated rules and the 3 custom rules. The `RUN DQ` results were:

| rule | table | type | total | valid | invalid |
|---|---|---|---|---|---|
| committed_within_on_hand | inventory | Custom Data Quality | 4 | 4 | 0 |
| margin_and_confidence_sane | channel_economics | Custom Data Quality | 14 | 14 | 0 |
| fulfilled_within_ordered | channel_order | Custom Data Quality | 1085 | 1085 | 0 |
| sku (FK, generated) | channel_order | Foreign Key Constraint | 1085 | 1085 | 0 |

`SHOW DQ INVALID RECORD committed_within_on_hand ...` returned 0 rows.

**Honest note: every rule passes.** The current synthetic data is clean (committed is 0 on every SKU), so these runs prove the rules work end to end but do not show a rule catching bad data. To see a failure, place orders in the demo until `committed` is non-zero and then edit `demo/data/wms_inventory.json` so `committed > on_hand`. That was not done here, so the shared demo data was not changed.

### Platform behaviour found while building this

- **Re-running `COMPILE USL IF NOT EXISTS ... DEPLOY` on an existing USL succeeds but silently deletes every custom DQ rule.** Primary-key and FK rules and table activations survive. This was tested directly: `LIST DQ USL` showed the 3 custom rules before the re-compile and none after. Because `usl_create.sql` re-registers all its rules after the compile, a full re-run of the file is safe. Running only the compile is not.
- **`REGISTER DQ` with an existing rule name behaves like an upsert.** It does not create a duplicate.
- **`DESCRIBE DATASOURCE TABLE` on a Lightning REST table returns only registration metadata.** Use `DESCRIBE <db>.<table>` instead to see the column types Zetaris froze at registration.

---

## 2a. Time saved compared with hand-coding

`demo/zetaris/handcoded_equivalent.py` computes the same answers without Zetaris. It reads the three Postgres tables with `psycopg` and the five REST endpoints with `urllib`, then produces the sellable units, channel scores, proportional split and all four DQ checks. It also compares its answers with the captured USL results: **`agrees_with_usl: {'sellable_7d': True, 'proposed_units': True}`**.

| | Zetaris USL | Hand-coded Python |
|---|---|---|
| Code for this deliverable (non-blank, non-comment lines) | 97 (`usl_create.sql`) + 58 (`usl_queries.sql`) = 155 SQL | 132 Python |
| Source connectivity code | 0 new lines; reused the ~50 lines of registration SQL that already existed | Written inline: 1 DB driver plus 5 REST calls, each with its own JSON shape |
| Wall-clock run time | About 8.4 s for the 4 USL queries (1.25 to 2.59 s each); 26 s for all 8 files including setup and DQ | 0.57 s total (0.565 s extract, 0.002 s transform) |
| Data quality | 3 declared rules + 5 FK rules generated from the DDL; `RUN DQ` counts and `SHOW DQ INVALID RECORD` for free | 4 hand-written checks; anything more (e.g. listing failing records) is extra code |
| Who can reuse it | Any SQL or JDBC client, BI tool, or the OmniSmartAlloc agent, with no code change | Only Python callers that import this file |
| Schema contract | Declared types, PKs and FKs, plus a descriptions and ERD in the Zetaris GUI | Implicit in dict keys |

**Honest reading.** On raw line count the two are about even: the SQL is not shorter. On run time, hand-coding is about 15x faster here, because the data is tiny and sits on the same machine, while every Zetaris query pays Spark planning and REST fetch overhead. The real time saving comes from the work that does not have to be done:

1. **No new connectors.** Adding a sixth or seventh source to the hand-coded version means another driver, auth and pagination handling, and JSON-shape code. In the USL it is one activation `SELECT`.
2. **Integration is shared, not per consumer.** The allocator agent, the ops dashboard and an analyst all query `omnialloc.*` without each re-implementing the joins. The hand-coded version is effectively rewritten for every new consumer.
3. **Rules are declared, not coded.** The FK rules came free from the DDL.

Authoring effort was not timed with a stopwatch, so treat these figures as estimates. Writing and running the USL took roughly 30 minutes, including reading the syntax reference; no USL statement needed a second attempt. Writing the hand-coded equivalent took roughly 20 minutes, and the 1:1 agreement check was only possible because the USL answers already existed. For a single throwaway report, hand-coding is as fast or faster. The USL pays off from the second consumer, or the second new source, onwards.

## 2b. Where it helps and where it doesn't in real work

**Where it helps:**

- **One governed answer to "what can we sell, and where".** Ops, finance and the allocation agent read the same `inventory`, `channel_economics` and `channel_order` definitions. That ends disagreements like "your spreadsheet says 70, mine says 64".
- **Safer automation.** An agent that queries a declared, DQ-checked model is easier to trust than one that issues ad hoc SQL against raw REST blobs. A `committed_within_on_hand` failure can block allocation before stock is oversold.
- **Fast onboarding of new channels.** A new marketplace is one `UNION ALL` branch in the `channel_order` activation, not a new service.
- **No data copies.** The data stays federated, so there is no nightly ETL to break and no copy of order data to secure.

**Where it doesn't help, or gets in the way:**

- **Latency.** At 1 to 2.6 s per query on tiny data, the USL is fine for planning but too slow for per-order, sub-100 ms decisions. Those need a cache, materialization, or a service.
- **Fragile REST typing.** This is the biggest practical cost on this project (see 2c).
- **Tooling gaps.** The SQL Workspace splits on `;`, so a multi-table COMPILE needs a custom runner. A re-compile silently drops custom DQ rules. Self-joins on the same table return wrong rows. The parser rejects some valid Spark SQL shapes (the `LATERAL VIEW` join above). Each of these cost debugging time.
- **Business logic still lives somewhere else.** The USL holds the model and data rules. The allocation optimisation itself stays in Python.

**Project and time-savings forecast.** These are assumptions, not measurements. Picture a mid-size multichannel retailer with 8 sales channels, 2 warehouses, about 15 suppliers and 3 consumers of allocation data (the agent, an ops dashboard and finance reporting):

| Work item | Hand-coded estimate | USL estimate |
|---|---|---|
| Initial integration of about 12 sources | 12 connectors at about 1 day each = 12 days | Registration plus activations at about 0.25 day each = 3 days |
| Each additional consumer | 2 to 3 days to re-implement joins and checks | About 0.5 day (write SQL against the model) |
| Each new channel added later | About 1.5 days | About 0.25 day |
| Ongoing schema-drift fixes (today) | About 0.5 day per incident | Also about 0.5 day per incident, and worse: one bad record fails the whole query (2c) |

With 3 consumers and 4 new channels a year, the first year comes to roughly 12 + 3x2.5 + 4x1.5 = **25.5 days hand-coded** against 3 + 3x0.5 + 4x0.25 = **5.5 days with the USL**, a saving of about 20 engineer-days. Most of that saving is lost if REST schema drift is not fixed, which leads to the requirement below.

## 2c. Killer requirement (PM view): REST schema drift tolerance

**Problem.** When a Lightning REST table is registered, Zetaris infers column types from the sample response and **freezes** them. If a later response contains one value of a different type, **the whole query fails**: no partial result, no row-level error, no DQ hook. This happened twice on this project, and both times the allocation agent was down until a code workaround shipped:

1. **Integer vs float.** `CHANNEL_ANALYTICS` margins and velocities were registered as `double`. When a later response carried a whole number (`"v7": 3` next to `"v7": 2.5`), every query on the table failed with:
   `ClassCastException: java.lang.Long cannot be cast to java.lang.Double`
   Workaround: `demo/mock_apis.py` now forces every decimal field to be a JSON float (`FLOAT_FIELDS`). Real third-party APIs will not do that for us.
2. **Object inside a string array.** `AMAZON_API.orders_raw.partial_shipments` was registered while every order had an empty list, so Zetaris froze it as `array<string>`. That is visible in the `DESCRIBE` output in 1b. The first order with a real partial shipment (an object) failed every query on the table, even queries that never select that column:
   `GenericRowWithSchema cannot be converted to the string type`
   Workaround: the mock API now serialises each entry to JSON text.

The fixes needed to recover are `DROP` plus re-register, which also breaks dependent SchemaStore views and USL activations. Re-registering also means the type is re-inferred from whatever sample comes back next time, so the problem can recur.

**Requirement.** *A REST-backed table must keep answering queries when the upstream JSON changes in type-compatible or additive ways. Values that cannot be reconciled must be quarantined per record, not fail the query.*

Acceptance criteria:

1. **Numeric widening.** If a column is `double` and a value is an integer, Zetaris coerces it silently, and the reverse widens the column (`bigint` to `double`).
2. **Nested-to-text fallback.** If an `array<string>` or `string` column receives an object or array, Zetaris stores the value as JSON text instead of failing.
3. **Per-record quarantine.** Any other mismatch sets the field to NULL, and the record is counted in a system DQ rule. Queries never fail because of a type mismatch.
4. **Additive schema evolution.** New fields can be added with one command, without dropping the table or breaking dependent views and USL activations.
5. **Visibility.** A drift log records when, which column, the old and new type, and the record count.

**Mock feature design.** None of the following exists today; it is a proposal.

```sql
-- Registration with an explicit drift policy (new SCHEMA POLICY clause)
CREATE LIGHTNING REST TABLE economics_raw FROM CHANNEL_ANALYTICS REQUEST(
    endpoint "http://host.docker.internal:8901/api/channels/economics",
    method "get", response_type "json", http_encoding "URLENCODED"
) HEADER (user-agent "omnismartalloc hackathon@local.dev") BODY ()
SCHEMA POLICY (numeric "widen", nested_mismatch "as_json", other_mismatch "null_and_flag", new_fields "evolve");

-- Additive evolution in place, keeping dependent views and USL activations valid
REFRESH LIGHTNING REST TABLE CHANNEL_ANALYTICS.economics_raw EVOLVE SCHEMA;

-- Drift history
SHOW SCHEMA DRIFT CHANNEL_ANALYTICS.economics_raw;
--  detected_at          | column                     | registered_type | observed_type | records | action
--  2026-10-20 09:14 UTC | economics.v7               | double          | bigint        | 3       | widened
--  2026-10-22 16:02 UTC | orders.partial_shipments   | array<string>   | struct<...>   | 1       | stored_as_json
```

**What the USL would look like with this feature.** The USL's declared types become the contract, and activation coerces to them instead of inheriting whatever the REST sample froze:

```sql
ACTIVATE USL TABLE lightning.metastore.omni_usl.omnialloc.channel_economics
WITH COERCION (on_mismatch "null_and_flag")              -- proposed clause
AS SELECT ... FROM CHANNEL_ANALYTICS.economics_raw LATERAL VIEW explode(economics) AS e;

LIST DQ USL lightning.metastore.omni_usl.omnialloc;
--  name                 | table             | type                       | expression
--  __schema_conformance | channel_economics | System Data Quality (auto) | all columns coerced without loss
--  margin_and_confidence_sane | channel_economics | Custom Data Quality | unit_margin >= 0 AND ...

RUN DQ __schema_conformance TABLE lightning.metastore.omni_usl.omnialloc.channel_economics;
--  name                 | table             | total_record | valid_record | invalid_record
--  __schema_conformance | channel_economics | 14           | 13           | 1
```

With this in place, both incidents on this project would have become a `RUN DQ` count of 1 invalid record, visible on a dashboard, instead of an outage. The allocator could then decide what to do: skip that SKU, use a fallback value, or alert a human. Today it has no way to decide, because it never gets a result. This is the single change that would make the 2b time savings hold up in production. Without it, every REST source is a standing outage risk, and teams fall back to hand-coded ingestion, which is exactly what the USL is meant to replace.

---

## Status and caveats

- **Succeeded:** 18/18 exploratory statements in the final run, 20/20 USL create statements (first run and full re-run), 4/4 USL queries, and the hand-coded run with an agreement check against the USL (both `True`).
- **Failed, then fixed:** one exploratory join, with the parser error quoted in 1b.
- **Not demonstrated:** a DQ rule catching a bad record (the data is clean), and a live reproduction of the two schema-drift errors. Their error strings come from this project's earlier incidents, recorded in `demo/mock_apis.py`. No throwaway REST tables were registered, to avoid side effects on the shared instance.
- **Runtime state:** the results reflect demo data on 27 October 2026. The demo server updates orders and inventory, so later runs will show different counts.
- **Scope of changes on the instance:** created namespace `lightning.metastore.omni_usl` (and ran `CREATE NAMESPACE IF NOT EXISTS lightning.metastore`), USL `omnialloc` with 6 activated tables and 3 custom DQ rules. No existing datasource, view or other project's object was changed. To tear down: `REMOVE USL omnialloc NAMESPACE lightning.metastore.omni_usl`.
