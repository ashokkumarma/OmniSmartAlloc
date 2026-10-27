-- Exploratory queries: CHANNEL_DB (Postgres over JDBC; DTC, Etsy and Walmart order tables).
-- Synthetic demo data. Run: python demo/zetaris/run_usl.py demo/zetaris/explore_channel_db.sql

-- @title CHANNEL_DB: tables registered from the Postgres datasource
SHOW DATASOURCE TABLES CHANNEL_DB;

-- @title CHANNEL_DB: column types of dtc_orders (etsy/walmart share the same shape)
DESCRIBE DATASOURCE TABLE CHANNEL_DB.dtc_orders;

-- @title CHANNEL_DB: orders, units and unfulfilled units per channel table and status
SELECT 'DTC' AS channel, status, COUNT(*) AS orders, SUM(qty) AS units, SUM(qty - fulfilled_qty) AS open_units
FROM CHANNEL_DB.dtc_orders GROUP BY status
UNION ALL
SELECT 'Etsy' AS channel, status, COUNT(*), SUM(qty), SUM(qty - fulfilled_qty)
FROM CHANNEL_DB.etsy_orders GROUP BY status
UNION ALL
SELECT 'Walmart' AS channel, status, COUNT(*), SUM(qty), SUM(qty - fulfilled_qty)
FROM CHANNEL_DB.walmart_orders GROUP BY status
ORDER BY channel, status;
