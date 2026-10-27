# Results: usl_queries.sql

Run 2026-10-27 13:35 UTC over JDBC. 4/4 statements succeeded. Rows shown are capped at 200.

## 1. Every USL table is active and returns live rows from its source

```sql
SELECT 'sku' AS usl_table, COUNT(*) AS row_count FROM lightning.metastore.omni_usl.omnialloc.sku
UNION ALL SELECT 'supplier', COUNT(*) FROM lightning.metastore.omni_usl.omnialloc.supplier
UNION ALL SELECT 'inventory', COUNT(*) FROM lightning.metastore.omni_usl.omnialloc.inventory
UNION ALL SELECT 'inbound_po', COUNT(*) FROM lightning.metastore.omni_usl.omnialloc.inbound_po
UNION ALL SELECT 'channel_economics', COUNT(*) FROM lightning.metastore.omni_usl.omnialloc.channel_economics
UNION ALL SELECT 'channel_order', COUNT(*) FROM lightning.metastore.omni_usl.omnialloc.channel_order
```

OK in 2.47s, 6 row(s).

| usl_table | row_count |
|---|---|
| sku | 4 |
| supplier | 3 |
| inventory | 4 |
| inbound_po | 6 |
| channel_economics | 14 |
| channel_order | 1085 |

## 2. Sellable units per SKU: free stock + supplier-risk-weighted inbound, blocked if the SKU is locked

```sql
SELECT i.sku,
       i.on_hand,
       i.committed,
       i.on_hand - i.committed AS free_now,
       COALESCE(p.inbound_units, 0) AS inbound_units,
       COALESCE(p.expected_inbound_7d, 0) AS expected_inbound_7d,
       CASE WHEN s.locked OR s.manual_override THEN 0
            ELSE i.on_hand - i.committed + COALESCE(p.expected_inbound_7d, 0) END AS sellable_7d,
       s.locked OR s.manual_override AS blocked,
       s.promo_multiplier
FROM lightning.metastore.omni_usl.omnialloc.inventory i
JOIN lightning.metastore.omni_usl.omnialloc.sku s ON s.sku = i.sku
LEFT JOIN (
    SELECT b.sku,
           SUM(b.qty) AS inbound_units,
           ROUND(SUM(CASE WHEN b.eta_days + (1 - sp.on_time_rate) * sp.typical_delay_days <= 7
                          THEN b.qty * sp.on_time_rate ELSE 0 END), 1) AS expected_inbound_7d
    FROM lightning.metastore.omni_usl.omnialloc.inbound_po b
    JOIN lightning.metastore.omni_usl.omnialloc.supplier sp ON sp.supplier = b.supplier
    GROUP BY b.sku
) p ON p.sku = i.sku
ORDER BY i.sku
```

OK in 2.11s, 4 row(s).

| sku | on_hand | committed | free_now | inbound_units | expected_inbound_7d | sellable_7d | blocked | promo_multiplier |
|---|---|---|---|---|---|---|---|---|
| LAMP-002 | 24 | 0 | 24 | 400 | 340.0 | 364.0 | False | 1.0 |
| LOCK-004 | 75 | 0 | 75 | 200 | 160.0 | 235.0 | False | 1.0 |
| MUG-001 | 70 | 0 | 70 | 200 | 160.0 | 230.0 | False | 1.0 |
| RUG-003 | 30 | 0 | 30 | 400 | 160.0 | 190.0 | False | 1.0 |

## 3. Channel scores per SKU (margin x velocity x confidence x promo) with open order demand from all four channels

```sql
SELECT e.sku,
       e.channel,
       e.unit_margin,
       e.v30,
       e.demand_confidence,
       ROUND(e.unit_margin * e.v30 * e.demand_confidence * COALESCE(s.promo_multiplier, 1.0), 1) AS channel_score,
       COALESCE(o.orders, 0) AS orders_seen,
       COALESCE(o.open_units, 0) AS open_units,
       RANK() OVER (PARTITION BY e.sku
                    ORDER BY e.unit_margin * e.v30 * e.demand_confidence * COALESCE(s.promo_multiplier, 1.0) DESC) AS channel_rank
FROM lightning.metastore.omni_usl.omnialloc.channel_economics e
LEFT JOIN lightning.metastore.omni_usl.omnialloc.sku s ON s.sku = e.sku
LEFT JOIN (
    SELECT sku, channel, COUNT(*) AS orders, SUM(qty - fulfilled_qty) AS open_units
    FROM lightning.metastore.omni_usl.omnialloc.channel_order
    GROUP BY sku, channel
) o ON o.sku = e.sku AND o.channel = e.channel
ORDER BY e.sku, channel_rank
```

OK in 2.59s, 14 row(s).

| sku | channel | unit_margin | v30 | demand_confidence | channel_score | orders_seen | open_units | channel_rank |
|---|---|---|---|---|---|---|---|---|
| LAMP-002 | DTC | 14.0 | 2.333333 | 0.9 | 29.4 | 218 | 9 | 1 |
| LAMP-002 | Amazon | 6.0 | 2.7 | 1.0 | 16.2 | 262 | 0 | 2 |
| LAMP-002 | Etsy | 11.0 | 1.0 | 0.8 | 8.8 | 97 | 0 | 3 |
| LAMP-002 | Walmart | 5.0 | 1.0 | 0.9 | 4.5 | 98 | 1 | 4 |
| LOCK-004 | Amazon | 20.0 | 2.0 | 1.0 | 40.0 | 18 | 0 | 1 |
| LOCK-004 | DTC | 30.0 | 1.0 | 0.9 | 27.0 | 16 | 6 | 2 |
| MUG-001 | Amazon | 16.0 | 14.0 | 1.0 | 224.0 | 60 | 16 | 1 |
| MUG-001 | DTC | 24.0 | 6.0 | 0.9 | 129.6 | 98 | 20 | 2 |
| MUG-001 | Walmart | 10.0 | 7.0 | 0.9 | 63.0 | 112 | 22 | 3 |
| MUG-001 | Etsy | 13.0 | 3.0 | 0.8 | 31.2 | 44 | 4 | 4 |
| RUG-003 | DTC | 112.0 | 2.0 | 0.9 | 201.6 | 32 | 0 | 1 |
| RUG-003 | Amazon | 75.0 | 2.0 | 1.0 | 150.0 | 18 | 6 | 2 |
| RUG-003 | Etsy | 60.0 | 0.5 | 0.6 | 18.0 | 6 | 1 | 3 |
| RUG-003 | Walmart | 45.0 | 0.5 | 0.7 | 15.7 | 6 | 3 | 4 |

## 4. Proposed split of free stock across channels, proportional to channel score (one query, three sources)

```sql
SELECT e.sku,
       e.channel,
       i.on_hand - i.committed AS free_now,
       ROUND(e.unit_margin * e.v30 * e.demand_confidence * s.promo_multiplier, 1) AS channel_score,
       CASE WHEN s.locked OR s.manual_override THEN 0
            ELSE FLOOR((i.on_hand - i.committed)
                       * (e.unit_margin * e.v30 * e.demand_confidence)
                       / SUM(e.unit_margin * e.v30 * e.demand_confidence) OVER (PARTITION BY e.sku)) END AS proposed_units
FROM lightning.metastore.omni_usl.omnialloc.channel_economics e
JOIN lightning.metastore.omni_usl.omnialloc.inventory i ON i.sku = e.sku
JOIN lightning.metastore.omni_usl.omnialloc.sku s ON s.sku = e.sku
ORDER BY e.sku, proposed_units DESC
```

OK in 1.25s, 14 row(s).

| sku | channel | free_now | channel_score | proposed_units |
|---|---|---|---|---|
| LAMP-002 | DTC | 24 | 29.4 | 11 |
| LAMP-002 | Amazon | 24 | 16.2 | 6 |
| LAMP-002 | Etsy | 24 | 8.8 | 3 |
| LAMP-002 | Walmart | 24 | 4.5 | 1 |
| LOCK-004 | Amazon | 75 | 40.0 | 44 |
| LOCK-004 | DTC | 75 | 27.0 | 30 |
| MUG-001 | Amazon | 70 | 224.0 | 35 |
| MUG-001 | DTC | 70 | 129.6 | 20 |
| MUG-001 | Walmart | 70 | 63.0 | 9 |
| MUG-001 | Etsy | 70 | 31.2 | 4 |
| RUG-003 | DTC | 30 | 201.6 | 15 |
| RUG-003 | Amazon | 30 | 150.0 | 11 |
| RUG-003 | Walmart | 30 | 15.7 | 1 |
| RUG-003 | Etsy | 30 | 18.0 | 1 |
