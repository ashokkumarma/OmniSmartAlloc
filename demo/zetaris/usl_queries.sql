-- =============================================================================
-- Queries over the ACTIVE OmniSmartAlloc USL (lightning.metastore.omni_usl.omnialloc).
-- These read only semantic-layer tables; Zetaris resolves each one to its federated source
-- (Postgres over JDBC + five REST APIs) at query time. Each query reads every USL table at most once.
-- Run: python demo/zetaris/run_usl.py demo/zetaris/usl_queries.sql
-- =============================================================================

-- @title Every USL table is active and returns live rows from its source
SELECT 'sku' AS usl_table, COUNT(*) AS row_count FROM lightning.metastore.omni_usl.omnialloc.sku
UNION ALL SELECT 'supplier', COUNT(*) FROM lightning.metastore.omni_usl.omnialloc.supplier
UNION ALL SELECT 'inventory', COUNT(*) FROM lightning.metastore.omni_usl.omnialloc.inventory
UNION ALL SELECT 'inbound_po', COUNT(*) FROM lightning.metastore.omni_usl.omnialloc.inbound_po
UNION ALL SELECT 'channel_economics', COUNT(*) FROM lightning.metastore.omni_usl.omnialloc.channel_economics
UNION ALL SELECT 'channel_order', COUNT(*) FROM lightning.metastore.omni_usl.omnialloc.channel_order;

-- @title Sellable units per SKU: free stock + supplier-risk-weighted inbound, blocked if the SKU is locked
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
ORDER BY i.sku;

-- @title Channel scores per SKU (margin x velocity x confidence x promo) with open order demand from all four channels
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
ORDER BY e.sku, channel_rank;

-- @title Proposed split of free stock across channels, proportional to channel score (one query, three sources)
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
ORDER BY e.sku, proposed_units DESC;
