-- Exploratory queries: RULES_ENGINE (Lightning REST table of per-SKU business rules).

-- @title RULES_ENGINE: column types Zetaris froze for the raw REST table
DESCRIBE RULES_ENGINE.rules_raw;

-- @title RULES_ENGINE: per-SKU locks, overrides, clearance and promotion multipliers
SELECT r.sku, r.locked, r.manual_override, r.clearance, r.promo_multiplier
FROM RULES_ENGINE.rules_raw LATERAL VIEW explode(rules) AS r
ORDER BY r.sku;

-- @title RULES_ENGINE: how many SKUs each rule blocks or boosts
SELECT SUM(CASE WHEN r.locked OR r.manual_override THEN 1 ELSE 0 END) AS skus_blocked,
       SUM(CASE WHEN r.clearance THEN 1 ELSE 0 END) AS skus_on_clearance,
       SUM(CASE WHEN r.promo_multiplier > 1 THEN 1 ELSE 0 END) AS skus_promoted,
       COUNT(*) AS skus_total
FROM RULES_ENGINE.rules_raw LATERAL VIEW explode(rules) AS r;
