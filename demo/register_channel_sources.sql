-- OmniSmartAlloc: register the per-channel ORDER sources in Zetaris (WRITES to the instance).
-- Two different source types, federated into one queryable layer:
--   CHANNEL_DB  = Postgres (JDBC) with dtc_orders, etsy_orders, walmart_orders
--   AMAZON_API  = Amazon seller REST API
-- Run with: python scripts/register_demo_sources.py --file demo/register_channel_sources.sql --execute

CREATE DATASOURCE CHANNEL_DB DESCRIBE BY "DTC-Etsy-Walmart-order-database" OPTIONS (
    jdbcdriver "org.postgresql.Driver",
    jdbcurl "jdbc:postgresql://omni-channels-db:5432/channels",
    username "omni",
    password "${CHANNELS_DB_PASSWORD}",
    fetchsize "1000"
);

REGISTER DATASOURCE TABLES FROM CHANNEL_DB;

CREATE LIGHTNING DATABASE AMAZON_API DESCRIBE BY "Amazon-seller-central-orders-REST-API";
CREATE LIGHTNING REST TABLE orders_raw FROM AMAZON_API REQUEST(
    endpoint "http://host.docker.internal:8901/api/amazon/orders",
    method "get", response_type "json", http_encoding "URLENCODED"
) HEADER (user-agent "omnismartalloc hackathon@local.dev") BODY ();

CREATE SCHEMASTORE VIEW amazon_orders WITH CONTAINER omnismart AS
SELECT o.id, o.ts, o.sku, o.qty, o.fulfilled_qty, o.status
FROM AMAZON_API.orders_raw LATERAL VIEW explode(orders) AS o;
