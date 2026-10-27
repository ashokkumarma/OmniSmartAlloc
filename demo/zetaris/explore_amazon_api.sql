-- Exploratory queries: AMAZON_API (Lightning REST table over the Amazon seller orders endpoint).

-- @title AMAZON_API: REST tables in the Lightning database
SHOW LIGHTNING TABLES AMAZON_API;

-- @title AMAZON_API: column types Zetaris froze for the raw REST table at registration
DESCRIBE AMAZON_API.orders_raw;

-- @title AMAZON_API: orders and units per SKU and status, flattened from the JSON array
SELECT o.sku, o.status, COUNT(*) AS orders, SUM(o.qty) AS units, SUM(o.qty - o.fulfilled_qty) AS open_units,
       MIN(o.ts) AS first_ts, MAX(o.ts) AS last_ts
FROM AMAZON_API.orders_raw LATERAL VIEW explode(orders) AS o
GROUP BY o.sku, o.status
ORDER BY o.sku, o.status;
