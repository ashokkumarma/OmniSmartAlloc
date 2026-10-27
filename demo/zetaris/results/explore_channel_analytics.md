# Results: explore_channel_analytics.sql

Run 2026-10-27 13:35 UTC over JDBC. 3/3 statements succeeded. Rows shown are capped at 200.

## 1. CHANNEL_ANALYTICS: column types Zetaris froze for the raw REST table

```sql
DESCRIBE CHANNEL_ANALYTICS.economics_raw
```

OK in 0.04s, 1 row(s).

| col_name | data_type | comment |
|---|---|---|
| economics | array<struct<channel:string,demand_confidence:double,floor_units:bigint,margin_age_hours:bigint,sku:string,trend:double,unit_margin:double,v30:double,v7:doub... |  |

## 2. CHANNEL_ANALYTICS: margin, velocity and confidence per SKU and channel

```sql
SELECT e.sku, e.channel, e.unit_margin, e.demand_confidence, e.v7, e.v30, e.v90, e.trend, e.floor_units
FROM CHANNEL_ANALYTICS.economics_raw LATERAL VIEW explode(economics) AS e
ORDER BY e.sku, e.unit_margin DESC
```

OK in 0.4s, 14 row(s).

| sku | channel | unit_margin | demand_confidence | v7 | v30 | v90 | trend | floor_units |
|---|---|---|---|---|---|---|---|---|
| LAMP-002 | DTC | 14.0 | 0.9 | 3.428571 | 2.333333 | 2.111111 | 1.0 | 0 |
| LAMP-002 | Etsy | 11.0 | 0.8 | 1.0 | 1.0 | 1.0 | 1.0 | 0 |
| LAMP-002 | Amazon | 6.0 | 1.0 | 1.714286 | 2.7 | 2.9 | 1.0 | 0 |
| LAMP-002 | Walmart | 5.0 | 0.9 | 1.0 | 1.0 | 1.0 | 1.0 | 0 |
| LOCK-004 | DTC | 30.0 | 0.9 | 1.0 | 1.0 | 1.0 | 1.0 | 0 |
| LOCK-004 | Amazon | 20.0 | 1.0 | 2.0 | 2.0 | 2.0 | 1.0 | 0 |
| MUG-001 | DTC | 24.0 | 0.9 | 6.0 | 6.0 | 6.0 | 1.0 | 0 |
| MUG-001 | Amazon | 16.0 | 1.0 | 14.0 | 14.0 | 14.0 | 1.0 | 0 |
| MUG-001 | Etsy | 13.0 | 0.8 | 3.0 | 3.0 | 3.0 | 1.0 | 0 |
| MUG-001 | Walmart | 10.0 | 0.9 | 7.0 | 7.0 | 7.0 | 1.0 | 0 |
| RUG-003 | DTC | 112.0 | 0.9 | 2.0 | 2.0 | 2.0 | 1.0 | 0 |
| RUG-003 | Amazon | 75.0 | 1.0 | 2.0 | 2.0 | 2.0 | 1.0 | 0 |
| RUG-003 | Etsy | 60.0 | 0.6 | 0.5 | 0.5 | 0.5 | 1.0 | 0 |
| RUG-003 | Walmart | 45.0 | 0.7 | 0.5 | 0.5 | 0.5 | 1.0 | 0 |

## 3. CHANNEL_ANALYTICS: best channel per SKU by expected 30-day margin (margin x velocity x confidence)

```sql
SELECT e.sku, e.channel, ROUND(e.unit_margin * e.v30 * e.demand_confidence, 1) AS expected_margin_30d,
       RANK() OVER (PARTITION BY e.sku ORDER BY e.unit_margin * e.v30 * e.demand_confidence DESC) AS rnk
FROM CHANNEL_ANALYTICS.economics_raw LATERAL VIEW explode(economics) AS e
ORDER BY e.sku, rnk
```

OK in 0.8s, 14 row(s).

| sku | channel | expected_margin_30d | rnk |
|---|---|---|---|
| LAMP-002 | DTC | 29.4 | 1 |
| LAMP-002 | Amazon | 16.2 | 2 |
| LAMP-002 | Etsy | 8.8 | 3 |
| LAMP-002 | Walmart | 4.5 | 4 |
| LOCK-004 | Amazon | 40.0 | 1 |
| LOCK-004 | DTC | 27.0 | 2 |
| MUG-001 | Amazon | 224.0 | 1 |
| MUG-001 | DTC | 129.6 | 2 |
| MUG-001 | Walmart | 63.0 | 3 |
| MUG-001 | Etsy | 31.2 | 4 |
| RUG-003 | DTC | 201.6 | 1 |
| RUG-003 | Amazon | 150.0 | 2 |
| RUG-003 | Etsy | 18.0 | 3 |
| RUG-003 | Walmart | 15.7 | 4 |
