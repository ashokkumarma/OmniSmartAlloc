-- =============================================================================
-- OmniSmartAlloc Unified Semantic Layer (USL): one governed model over six federated sources.
--
--   CHANNEL_DB        Postgres over JDBC: dtc_orders, etsy_orders, walmart_orders
--   AMAZON_API        REST: Amazon seller orders
--   WMS               REST: inventory_raw, inbound_raw
--   SUPPLIER_PORTAL   REST: supplier reliability
--   CHANNEL_ANALYTICS REST: per-SKU, per-channel margin / velocity / confidence
--   RULES_ENGINE      REST: per-SKU locks, overrides, clearance, promotions
--
-- Namespace: lightning.metastore.omni_usl   USL: omnialloc
-- Every table is keyed by sku (and channel / PO / order where needed); foreign keys back to sku and
-- supplier give the model an ERD and generate referential DQ rules automatically.
-- All data is synthetic. Run: python demo/zetaris/run_usl.py demo/zetaris/usl_create.sql
--
-- Notes:
--   * The COMPILE USL statement holds all CREATE TABLE definitions and must be sent as ONE statement;
--     run_usl.py merges the CREATE TABLE chunks back into the COMPILE statement before sending.
--   * Integer REST fields arrive as bigint and decimals as double, so the DDL declares bigint/double
--     (ACTIVATE refuses to downcast a query column to a narrower declared type).
--   * No activation reads the same source table twice (a known Lightning issue returns the first
--     read's rows for the second read of the same table in one query).
-- =============================================================================

-- @title Ensure the parent metastore namespace exists (no-op if it already does)
CREATE NAMESPACE IF NOT EXISTS lightning.metastore;

-- @title Create the project namespace
CREATE NAMESPACE IF NOT EXISTS lightning.metastore.omni_usl;

-- @title Compile and deploy the six-table OmniSmartAlloc model (one statement)
COMPILE USL IF NOT EXISTS omnialloc DEPLOY NAMESPACE lightning.metastore.omni_usl DDL
CREATE TABLE sku (
    sku varchar(64) NOT NULL PRIMARY KEY,
    locked boolean,
    manual_override boolean,
    clearance boolean,
    promo_multiplier double
);
CREATE TABLE supplier (
    supplier varchar(64) NOT NULL PRIMARY KEY,
    on_time_rate double,
    typical_delay_days bigint
);
CREATE TABLE inventory (
    sku varchar(64) NOT NULL PRIMARY KEY FOREIGN KEY REFERENCES sku(sku),
    on_hand bigint,
    committed bigint,
    unputaway bigint,
    age_hours double
);
CREATE TABLE inbound_po (
    po_line varchar(140) NOT NULL PRIMARY KEY,
    po varchar(64),
    sku varchar(64) FOREIGN KEY REFERENCES sku(sku),
    qty bigint,
    eta_days bigint,
    status varchar(32),
    supplier varchar(64) FOREIGN KEY REFERENCES supplier(supplier)
);
CREATE TABLE channel_economics (
    sku_channel varchar(140) NOT NULL PRIMARY KEY,
    sku varchar(64) FOREIGN KEY REFERENCES sku(sku),
    channel varchar(32),
    unit_margin double,
    demand_confidence double,
    v7 double,
    v30 double,
    v90 double,
    trend double,
    floor_units bigint,
    margin_age_hours bigint
);
CREATE TABLE channel_order (
    order_key varchar(140) NOT NULL PRIMARY KEY,
    channel varchar(32),
    order_id varchar(64),
    sku varchar(64) FOREIGN KEY REFERENCES sku(sku),
    ts varchar(40),
    qty bigint,
    fulfilled_qty bigint,
    status varchar(32)
);

-- @title Activate sku from RULES_ENGINE (REST)
ACTIVATE USL TABLE lightning.metastore.omni_usl.omnialloc.sku AS
SELECT COALESCE(r.sku, '') AS sku, r.locked, r.manual_override, r.clearance, r.promo_multiplier
FROM RULES_ENGINE.rules_raw LATERAL VIEW explode(rules) AS r;

-- @title Activate supplier from SUPPLIER_PORTAL (REST)
ACTIVATE USL TABLE lightning.metastore.omni_usl.omnialloc.supplier AS
SELECT COALESCE(r.supplier, '') AS supplier, r.on_time_rate, r.typical_delay_days
FROM SUPPLIER_PORTAL.reliability_raw LATERAL VIEW explode(suppliers) AS r;

-- @title Activate inventory from WMS inventory_raw (REST)
ACTIVATE USL TABLE lightning.metastore.omni_usl.omnialloc.inventory AS
SELECT COALESCE(i.sku, '') AS sku, i.on_hand, i.committed, i.unputaway, i.age_hours
FROM WMS.inventory_raw LATERAL VIEW explode(inventory) AS i;

-- @title Activate inbound_po from WMS inbound_raw (REST)
ACTIVATE USL TABLE lightning.metastore.omni_usl.omnialloc.inbound_po AS
SELECT COALESCE(concat(s.po, '|', s.sku), '') AS po_line, s.po, s.sku, s.qty, s.eta_days, s.status, s.supplier
FROM WMS.inbound_raw LATERAL VIEW explode(inbound) AS s;

-- @title Activate channel_economics from CHANNEL_ANALYTICS (REST)
ACTIVATE USL TABLE lightning.metastore.omni_usl.omnialloc.channel_economics AS
SELECT COALESCE(concat(e.sku, '|', e.channel), '') AS sku_channel, e.sku, e.channel, e.unit_margin,
       e.demand_confidence, e.v7, e.v30, e.v90, e.trend, e.floor_units, e.margin_age_hours
FROM CHANNEL_ANALYTICS.economics_raw LATERAL VIEW explode(economics) AS e;

-- @title Activate channel_order: Postgres (3 tables over JDBC) UNION Amazon (REST) in one federated query
ACTIVATE USL TABLE lightning.metastore.omni_usl.omnialloc.channel_order AS
SELECT COALESCE(concat('DTC:', id), '') AS order_key, 'DTC' AS channel, id AS order_id, sku, ts,
       CAST(qty AS bigint) AS qty, CAST(fulfilled_qty AS bigint) AS fulfilled_qty, status
FROM CHANNEL_DB.dtc_orders
UNION ALL
SELECT COALESCE(concat('Etsy:', id), ''), 'Etsy', id, sku, ts, CAST(qty AS bigint), CAST(fulfilled_qty AS bigint), status
FROM CHANNEL_DB.etsy_orders
UNION ALL
SELECT COALESCE(concat('Walmart:', id), ''), 'Walmart', id, sku, ts, CAST(qty AS bigint), CAST(fulfilled_qty AS bigint), status
FROM CHANNEL_DB.walmart_orders
UNION ALL
SELECT COALESCE(concat('Amazon:', o.id), ''), 'Amazon', o.id, o.sku, o.ts, o.qty, o.fulfilled_qty, o.status
FROM AMAZON_API.orders_raw LATERAL VIEW explode(orders) AS o;

-- @title Document the model
UPDATE USL lightning.metastore.omni_usl.omnialloc.inventory SET TABLE DESCRIPTION One row per SKU of warehouse stock from the WMS REST API. committed must never exceed on_hand;

-- @title DQ rule: committed stock can never exceed on-hand stock (and neither may be missing or negative)
REGISTER DQ committed_within_on_hand TABLE lightning.metastore.omni_usl.omnialloc.inventory AS
on_hand IS NOT NULL AND committed IS NOT NULL AND committed >= 0 AND committed <= on_hand;

-- @title DQ rule: a channel may never be scored with a negative unit margin or confidence outside 0..1
REGISTER DQ margin_and_confidence_sane TABLE lightning.metastore.omni_usl.omnialloc.channel_economics AS
unit_margin >= 0 AND demand_confidence >= 0 AND demand_confidence <= 1;

-- @title DQ rule: an order can never be fulfilled beyond its ordered quantity
REGISTER DQ fulfilled_within_ordered TABLE lightning.metastore.omni_usl.omnialloc.channel_order AS
fulfilled_qty >= 0 AND fulfilled_qty <= qty;

-- @title List every key constraint and DQ rule in the USL
LIST DQ USL lightning.metastore.omni_usl.omnialloc;

-- @title RUN DQ: committed_within_on_hand on inventory
RUN DQ committed_within_on_hand TABLE lightning.metastore.omni_usl.omnialloc.inventory;

-- @title RUN DQ: margin_and_confidence_sane on channel_economics
RUN DQ margin_and_confidence_sane TABLE lightning.metastore.omni_usl.omnialloc.channel_economics;

-- @title RUN DQ: fulfilled_within_ordered on channel_order
RUN DQ fulfilled_within_ordered TABLE lightning.metastore.omni_usl.omnialloc.channel_order;

-- @title RUN DQ: the FK-generated rule channel_order.sku -> sku (every order SKU exists in the SKU master)
RUN DQ sku TABLE lightning.metastore.omni_usl.omnialloc.channel_order;

-- @title SHOW DQ: inventory rows failing the committed_within_on_hand rule
SHOW DQ INVALID RECORD committed_within_on_hand TABLE lightning.metastore.omni_usl.omnialloc.inventory;

-- @title Namespace now lists the activated tables
SHOW NAMESPACES OR TABLES IN lightning.metastore.omni_usl;
