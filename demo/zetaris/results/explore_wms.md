# Results: explore_wms.sql

Run 2026-10-27 13:34 UTC over JDBC. 3/3 statements succeeded. Rows shown are capped at 200.

## 1. WMS: REST tables in the Lightning database

```sql
SHOW LIGHTNING TABLES WMS
```

OK in 0.06s, 2 row(s).

| name | materialized_table | source_table | table_type | format | id |
|---|---|---|---|---|---|
| inbound_raw |  | http://host.docker.internal:8901/api/wms/inbound | rest |  | 994 |
| inventory_raw |  | http://host.docker.internal:8901/api/wms/inventory | rest |  | 987 |

## 2. WMS: on-hand, committed and free stock per SKU

```sql
SELECT i.sku, i.on_hand, i.committed, i.unputaway, i.age_hours, i.on_hand - i.committed AS free_units
FROM WMS.inventory_raw LATERAL VIEW explode(inventory) AS i
ORDER BY i.sku
```

OK in 0.84s, 4 row(s).

| sku | on_hand | committed | unputaway | age_hours | free_units |
|---|---|---|---|---|---|
| LAMP-002 | 24 | 0 | 0 | 0.2 | 24 |
| LOCK-004 | 75 | 0 | 0 | 0.2 | 75 |
| MUG-001 | 70 | 0 | 0 | 0.2 | 70 |
| RUG-003 | 30 | 0 | 0 | 0.2 | 30 |

## 3. WMS: inbound purchase-order lines per SKU and status

```sql
SELECT s.sku, s.status, COUNT(*) AS po_lines, SUM(s.qty) AS units, MIN(s.eta_days) AS soonest_eta_days
FROM WMS.inbound_raw LATERAL VIEW explode(inbound) AS s
GROUP BY s.sku, s.status
ORDER BY s.sku, s.status
```

OK in 1.14s, 5 row(s).

| sku | status | po_lines | units | soonest_eta_days |
|---|---|---|---|---|
| LAMP-002 | in_transit | 2 | 400 | 4 |
| LOCK-004 | in_transit | 1 | 200 | 5 |
| MUG-001 | in_transit | 1 | 200 | 5 |
| RUG-003 | in_transit | 1 | 200 | 5 |
| RUG-003 | planned | 1 | 200 | 40 |
