# Results: explore_channel_db.sql

Run 2026-10-27 13:34 UTC over JDBC. 3/3 statements succeeded. Rows shown are capped at 200.

## 1. CHANNEL_DB: tables registered from the Postgres datasource

```sql
SHOW DATASOURCE TABLES CHANNEL_DB
```

OK in 0.1s, 3 row(s).

| name | relation | source_table | partition clause | description | materialized table | datasource_id | relation_id |
|---|---|---|---|---|---|---|---|
| dtc_orders | Table | dtc_orders |  |  |  | 1060 | 1067 |
| etsy_orders | Table | etsy_orders |  |  |  | 1060 | 1068 |
| walmart_orders | Table | walmart_orders |  |  |  | 1060 | 1069 |

## 2. CHANNEL_DB: column types of dtc_orders (etsy/walmart share the same shape)

```sql
DESCRIBE DATASOURCE TABLE CHANNEL_DB.dtc_orders
```

OK in 0.1s, 7 row(s).

| col_name | data_type | comment | description | tags |
|---|---|---|---|---|
| id | string | PK, NOT NULL, Indexed(dtc_orders_pkey) |  |  |
| ts | string | NOT NULL |  |  |
| sku | string | NOT NULL |  |  |
| qty | integer | NOT NULL |  |  |
| fulfilled_qty | integer | NOT NULL |  |  |
| status | string | NOT NULL |  |  |
| partial_shipments | string | NOT NULL |  |  |

## 3. CHANNEL_DB: orders, units and unfulfilled units per channel table and status

```sql
SELECT 'DTC' AS channel, status, COUNT(*) AS orders, SUM(qty) AS units, SUM(qty - fulfilled_qty) AS open_units
FROM CHANNEL_DB.dtc_orders GROUP BY status
UNION ALL
SELECT 'Etsy' AS channel, status, COUNT(*), SUM(qty), SUM(qty - fulfilled_qty)
FROM CHANNEL_DB.etsy_orders GROUP BY status
UNION ALL
SELECT 'Walmart' AS channel, status, COUNT(*), SUM(qty), SUM(qty - fulfilled_qty)
FROM CHANNEL_DB.walmart_orders GROUP BY status
ORDER BY channel, status
```

OK in 1.14s, 8 row(s).

| channel | status | orders | units | open_units |
|---|---|---|---|---|
| DTC | cancelled | 15 | 26 | 26 |
| DTC | fulfilled | 346 | 481 | 0 |
| DTC | open | 3 | 9 | 9 |
| Etsy | cancelled | 5 | 5 | 5 |
| Etsy | fulfilled | 142 | 192 | 0 |
| Walmart | cancelled | 16 | 24 | 24 |
| Walmart | fulfilled | 198 | 294 | 0 |
| Walmart | open | 2 | 2 | 2 |
