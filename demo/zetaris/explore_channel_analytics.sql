-- Exploratory queries: CHANNEL_ANALYTICS (Lightning REST table of per-SKU, per-channel economics).

-- @title CHANNEL_ANALYTICS: column types Zetaris froze for the raw REST table
DESCRIBE CHANNEL_ANALYTICS.economics_raw;

-- @title CHANNEL_ANALYTICS: margin, velocity and confidence per SKU and channel
SELECT e.sku, e.channel, e.unit_margin, e.demand_confidence, e.v7, e.v30, e.v90, e.trend, e.floor_units
FROM CHANNEL_ANALYTICS.economics_raw LATERAL VIEW explode(economics) AS e
ORDER BY e.sku, e.unit_margin DESC;

-- @title CHANNEL_ANALYTICS: best channel per SKU by expected 30-day margin (margin x velocity x confidence)
SELECT e.sku, e.channel, ROUND(e.unit_margin * e.v30 * e.demand_confidence, 1) AS expected_margin_30d,
       RANK() OVER (PARTITION BY e.sku ORDER BY e.unit_margin * e.v30 * e.demand_confidence DESC) AS rnk
FROM CHANNEL_ANALYTICS.economics_raw LATERAL VIEW explode(economics) AS e
ORDER BY e.sku, rnk;
