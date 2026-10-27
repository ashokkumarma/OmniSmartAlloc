# Results: explore_rules_engine.sql

Run 2026-10-27 13:35 UTC over JDBC. 3/3 statements succeeded. Rows shown are capped at 200.

## 1. RULES_ENGINE: column types Zetaris froze for the raw REST table

```sql
DESCRIBE RULES_ENGINE.rules_raw
```

OK in 0.12s, 1 row(s).

| col_name | data_type | comment |
|---|---|---|
| rules | array<struct<clearance:boolean,locked:boolean,manual_override:boolean,promo_multiplier:double,sku:string>> |  |

## 2. RULES_ENGINE: per-SKU locks, overrides, clearance and promotion multipliers

```sql
SELECT r.sku, r.locked, r.manual_override, r.clearance, r.promo_multiplier
FROM RULES_ENGINE.rules_raw LATERAL VIEW explode(rules) AS r
ORDER BY r.sku
```

OK in 0.37s, 4 row(s).

| sku | locked | manual_override | clearance | promo_multiplier |
|---|---|---|---|---|
| LAMP-002 | False | False | False | 1.0 |
| LOCK-004 | False | False | False | 1.0 |
| MUG-001 | False | False | False | 1.0 |
| RUG-003 | False | False | False | 1.0 |

## 3. RULES_ENGINE: how many SKUs each rule blocks or boosts

```sql
SELECT SUM(CASE WHEN r.locked OR r.manual_override THEN 1 ELSE 0 END) AS skus_blocked,
       SUM(CASE WHEN r.clearance THEN 1 ELSE 0 END) AS skus_on_clearance,
       SUM(CASE WHEN r.promo_multiplier > 1 THEN 1 ELSE 0 END) AS skus_promoted,
       COUNT(*) AS skus_total
FROM RULES_ENGINE.rules_raw LATERAL VIEW explode(rules) AS r
```

OK in 0.29s, 1 row(s).

| skus_blocked | skus_on_clearance | skus_promoted | skus_total |
|---|---|---|---|
| 0 | 0 | 0 | 4 |
