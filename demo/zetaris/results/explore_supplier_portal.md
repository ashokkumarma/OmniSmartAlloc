# Results: explore_supplier_portal.sql

Run 2026-10-27 13:35 UTC over JDBC. 3/3 statements succeeded. Rows shown are capped at 200.

## 1. SUPPLIER_PORTAL: column types Zetaris froze for the raw REST table

```sql
DESCRIBE SUPPLIER_PORTAL.reliability_raw
```

OK in 0.09s, 1 row(s).

| col_name | data_type | comment |
|---|---|---|
| suppliers | array<struct<on_time_rate:double,supplier:string,typical_delay_days:bigint>> |  |

## 2. SUPPLIER_PORTAL: suppliers ranked by on-time rate

```sql
SELECT r.supplier, r.on_time_rate, r.typical_delay_days
FROM SUPPLIER_PORTAL.reliability_raw LATERAL VIEW explode(suppliers) AS r
ORDER BY r.on_time_rate DESC
```

OK in 0.51s, 3 row(s).

| supplier | on_time_rate | typical_delay_days |
|---|---|---|
| BRIGHT | 0.9 | 1 |
| ACME-EAST | 0.8 | 4 |
| KEYCO | 0.6 | 10 |

## 3. SUPPLIER_PORTAL x WMS: inbound units at risk, weighted by supplier lateness (cross-source join)

```sql
SELECT w.supplier, r.on_time_rate, SUM(w.qty) AS inbound_units,
       ROUND(SUM(w.qty) * (1 - r.on_time_rate), 1) AS units_likely_late
FROM (SELECT s.supplier, s.qty FROM WMS.inbound_raw LATERAL VIEW explode(inbound) AS s) w
JOIN (SELECT x.supplier, x.on_time_rate FROM SUPPLIER_PORTAL.reliability_raw LATERAL VIEW explode(suppliers) AS x) r
  ON r.supplier = w.supplier
GROUP BY w.supplier, r.on_time_rate
ORDER BY units_likely_late DESC
```

OK in 0.85s, 3 row(s).

| supplier | on_time_rate | inbound_units | units_likely_late |
|---|---|---|---|
| ACME-EAST | 0.8 | 800 | 160.0 |
| KEYCO | 0.6 | 200 | 80.0 |
| BRIGHT | 0.9 | 200 | 20.0 |
