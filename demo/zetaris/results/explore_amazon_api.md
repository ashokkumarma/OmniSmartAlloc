# Results: explore_amazon_api.sql

Run 2026-10-27 13:34 UTC over JDBC. 3/3 statements succeeded. Rows shown are capped at 200.

## 1. AMAZON_API: REST tables in the Lightning database

```sql
SHOW LIGHTNING TABLES AMAZON_API
```

OK in 0.05s, 1 row(s).

| name | materialized_table | source_table | table_type | format | id |
|---|---|---|---|---|---|
| orders_raw |  | http://host.docker.internal:8901/api/amazon/orders | rest |  | 1093 |

## 2. AMAZON_API: column types Zetaris froze for the raw REST table at registration

```sql
DESCRIBE AMAZON_API.orders_raw
```

OK in 0.08s, 1 row(s).

| col_name | data_type | comment |
|---|---|---|
| orders | array<struct<fulfilled_qty:bigint,id:string,partial_shipments:array<string>,qty:bigint,sku:string,status:string,ts:string>> |  |

## 3. AMAZON_API: orders and units per SKU and status, flattened from the JSON array

```sql
SELECT o.sku, o.status, COUNT(*) AS orders, SUM(o.qty) AS units, SUM(o.qty - o.fulfilled_qty) AS open_units,
       MIN(o.ts) AS first_ts, MAX(o.ts) AS last_ts
FROM AMAZON_API.orders_raw LATERAL VIEW explode(orders) AS o
GROUP BY o.sku, o.status
ORDER BY o.sku, o.status
```

OK in 0.99s, 6 row(s).

| sku | status | orders | units | open_units | first_ts | last_ts |
|---|---|---|---|---|---|---|
| LAMP-002 | fulfilled | 262 | 281 | 0 | 2026-07-27T04:00:00Z | 2026-10-26T23:37:39Z |
| LOCK-004 | fulfilled | 18 | 37 | 0 | 2026-07-30T17:40:17Z | 2026-09-27T23:40:44Z |
| MUG-001 | cancelled | 7 | 16 | 16 | 2026-07-28T22:33:02Z | 2026-10-11T14:55:09Z |
| MUG-001 | fulfilled | 53 | 130 | 0 | 2026-07-27T20:31:26Z | 2026-10-26T23:34:26Z |
| RUG-003 | cancelled | 3 | 6 | 6 | 2026-08-08T06:37:36Z | 2026-08-24T07:55:53Z |
| RUG-003 | fulfilled | 15 | 39 | 0 | 2026-08-08T12:25:16Z | 2026-10-22T11:00:42Z |
