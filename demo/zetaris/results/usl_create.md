# Results: usl_create.sql

Run 2026-10-27 13:35 UTC over JDBC. 20/20 statements succeeded. Rows shown are capped at 200.

## 1. Ensure the parent metastore namespace exists (no-op if it already does)

```sql
CREATE NAMESPACE IF NOT EXISTS lightning.metastore
```

OK in 0.04s, 0 row(s).

| Result |
|---|

## 2. Create the project namespace

```sql
CREATE NAMESPACE IF NOT EXISTS lightning.metastore.omni_usl
```

OK in 0.03s, 0 row(s).

| Result |
|---|

## 3. Compile and deploy the six-table OmniSmartAlloc model (one statement)

```sql
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
)
```

OK in 0.05s, 1 row(s).

| json |
|---|
| {"namespace":["metastore","omni_usl"],"name":"omnialloc","tables":[{"name":"sku","columnSpecs":[{"name":"sku","dataType":"\"varchar(64)\"","primaryKey":{"col... |

## 4. Activate sku from RULES_ENGINE (REST)

```sql
ACTIVATE USL TABLE lightning.metastore.omni_usl.omnialloc.sku AS
SELECT COALESCE(r.sku, '') AS sku, r.locked, r.manual_override, r.clearance, r.promo_multiplier
FROM RULES_ENGINE.rules_raw LATERAL VIEW explode(rules) AS r
```

OK in 0.1s, 1 row(s).

| registered |
|---|
| {"name":"sku","query":"SELECT COALESCE(r.sku, '') AS sku, r.locked, r.manual_override, r.clearance, r.promo_multiplier\nFROM RULES_ENGINE.rules_raw LATERAL V... |

## 5. Activate supplier from SUPPLIER_PORTAL (REST)

```sql
ACTIVATE USL TABLE lightning.metastore.omni_usl.omnialloc.supplier AS
SELECT COALESCE(r.supplier, '') AS supplier, r.on_time_rate, r.typical_delay_days
FROM SUPPLIER_PORTAL.reliability_raw LATERAL VIEW explode(suppliers) AS r
```

OK in 0.1s, 1 row(s).

| registered |
|---|
| {"name":"supplier","query":"SELECT COALESCE(r.supplier, '') AS supplier, r.on_time_rate, r.typical_delay_days\nFROM SUPPLIER_PORTAL.reliability_raw LATERAL V... |

## 6. Activate inventory from WMS inventory_raw (REST)

```sql
ACTIVATE USL TABLE lightning.metastore.omni_usl.omnialloc.inventory AS
SELECT COALESCE(i.sku, '') AS sku, i.on_hand, i.committed, i.unputaway, i.age_hours
FROM WMS.inventory_raw LATERAL VIEW explode(inventory) AS i
```

OK in 0.12s, 1 row(s).

| registered |
|---|
| {"name":"inventory","query":"SELECT COALESCE(i.sku, '') AS sku, i.on_hand, i.committed, i.unputaway, i.age_hours\nFROM WMS.inventory_raw LATERAL VIEW explode... |

## 7. Activate inbound_po from WMS inbound_raw (REST)

```sql
ACTIVATE USL TABLE lightning.metastore.omni_usl.omnialloc.inbound_po AS
SELECT COALESCE(concat(s.po, '|', s.sku), '') AS po_line, s.po, s.sku, s.qty, s.eta_days, s.status, s.supplier
FROM WMS.inbound_raw LATERAL VIEW explode(inbound) AS s
```

OK in 0.18s, 1 row(s).

| registered |
|---|
| {"name":"inbound_po","query":"SELECT COALESCE(concat(s.po, '\|', s.sku), '') AS po_line, s.po, s.sku, s.qty, s.eta_days, s.status, s.supplier\nFROM WMS.inbou... |

## 8. Activate channel_economics from CHANNEL_ANALYTICS (REST)

```sql
ACTIVATE USL TABLE lightning.metastore.omni_usl.omnialloc.channel_economics AS
SELECT COALESCE(concat(e.sku, '|', e.channel), '') AS sku_channel, e.sku, e.channel, e.unit_margin,
       e.demand_confidence, e.v7, e.v30, e.v90, e.trend, e.floor_units, e.margin_age_hours
FROM CHANNEL_ANALYTICS.economics_raw LATERAL VIEW explode(economics) AS e
```

OK in 0.07s, 1 row(s).

| registered |
|---|
| {"name":"channel_economics","query":"SELECT COALESCE(concat(e.sku, '\|', e.channel), '') AS sku_channel, e.sku, e.channel, e.unit_margin,\n       e.demand_co... |

## 9. Activate channel_order: Postgres (3 tables over JDBC) UNION Amazon (REST) in one federated query

```sql
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
FROM AMAZON_API.orders_raw LATERAL VIEW explode(orders) AS o
```

OK in 0.33s, 1 row(s).

| registered |
|---|
| {"name":"channel_order","query":"SELECT COALESCE(concat('DTC:', id), '') AS order_key, 'DTC' AS channel, id AS order_id, sku, ts,\n       CAST(qty AS bigint)... |

## 10. Document the model

```sql
UPDATE USL lightning.metastore.omni_usl.omnialloc.inventory SET TABLE DESCRIPTION One row per SKU of warehouse stock from the WMS REST API. committed must never exceed on_hand
```

OK in 0.06s, 1 row(s).

| updated |
|---|
| True |

## 11. DQ rule: committed stock can never exceed on-hand stock (and neither may be missing or negative)

```sql
REGISTER DQ committed_within_on_hand TABLE lightning.metastore.omni_usl.omnialloc.inventory AS
on_hand IS NOT NULL AND committed IS NOT NULL AND committed >= 0 AND committed <= on_hand
```

OK in 0.27s, 1 row(s).

| json |
|---|
| {"namespace":["metastore","omni_usl"],"name":"omnialloc","tables":[{"name":"sku","columnSpecs":[{"name":"sku","dataType":"\"varchar(64)\"","primaryKey":{"col... |

## 12. DQ rule: a channel may never be scored with a negative unit margin or confidence outside 0..1

```sql
REGISTER DQ margin_and_confidence_sane TABLE lightning.metastore.omni_usl.omnialloc.channel_economics AS
unit_margin >= 0 AND demand_confidence >= 0 AND demand_confidence <= 1
```

OK in 0.29s, 1 row(s).

| json |
|---|
| {"namespace":["metastore","omni_usl"],"name":"omnialloc","tables":[{"name":"sku","columnSpecs":[{"name":"sku","dataType":"\"varchar(64)\"","primaryKey":{"col... |

## 13. DQ rule: an order can never be fulfilled beyond its ordered quantity

```sql
REGISTER DQ fulfilled_within_ordered TABLE lightning.metastore.omni_usl.omnialloc.channel_order AS
fulfilled_qty >= 0 AND fulfilled_qty <= qty
```

OK in 1.05s, 1 row(s).

| json |
|---|
| {"namespace":["metastore","omni_usl"],"name":"omnialloc","tables":[{"name":"sku","columnSpecs":[{"name":"sku","dataType":"\"varchar(64)\"","primaryKey":{"col... |

## 14. List every key constraint and DQ rule in the USL

```sql
LIST DQ USL lightning.metastore.omni_usl.omnialloc
```

OK in 0.07s, 14 row(s).

| name | table | type | expression |
|---|---|---|---|
| sku | sku | Primary key constraints |  |
| supplier | supplier | Primary key constraints |  |
| sku | inventory | Primary key constraints |  |
| sku | inventory | Foreign key constraints |  |
| committed_within_on_hand | inventory | Custom Data Quality | on_hand IS NOT NULL AND committed IS NOT NULL AND committed >= 0 AND committed <= on_hand |
| po_line | inbound_po | Primary key constraints |  |
| sku | inbound_po | Foreign key constraints |  |
| supplier | inbound_po | Foreign key constraints |  |
| sku_channel | channel_economics | Primary key constraints |  |
| sku | channel_economics | Foreign key constraints |  |
| margin_and_confidence_sane | channel_economics | Custom Data Quality | unit_margin >= 0 AND demand_confidence >= 0 AND demand_confidence <= 1 |
| order_key | channel_order | Primary key constraints |  |
| sku | channel_order | Foreign key constraints |  |
| fulfilled_within_ordered | channel_order | Custom Data Quality | fulfilled_qty >= 0 AND fulfilled_qty <= qty |

## 15. RUN DQ: committed_within_on_hand on inventory

```sql
RUN DQ committed_within_on_hand TABLE lightning.metastore.omni_usl.omnialloc.inventory
```

OK in 0.67s, 1 row(s).

| name | table | type | total_record | valid_record | invalid_record |
|---|---|---|---|---|---|
| committed_within_on_hand | inventory | Custom Data Quality | 4 | 4 | 0 |

## 16. RUN DQ: margin_and_confidence_sane on channel_economics

```sql
RUN DQ margin_and_confidence_sane TABLE lightning.metastore.omni_usl.omnialloc.channel_economics
```

OK in 0.68s, 1 row(s).

| name | table | type | total_record | valid_record | invalid_record |
|---|---|---|---|---|---|
| margin_and_confidence_sane | channel_economics | Custom Data Quality | 14 | 14 | 0 |

## 17. RUN DQ: fulfilled_within_ordered on channel_order

```sql
RUN DQ fulfilled_within_ordered TABLE lightning.metastore.omni_usl.omnialloc.channel_order
```

OK in 1.65s, 1 row(s).

| name | table | type | total_record | valid_record | invalid_record |
|---|---|---|---|---|---|
| fulfilled_within_ordered | channel_order | Custom Data Quality | 1085 | 1085 | 0 |

## 18. RUN DQ: the FK-generated rule channel_order.sku -> sku (every order SKU exists in the SKU master)

```sql
RUN DQ sku TABLE lightning.metastore.omni_usl.omnialloc.channel_order
```

OK in 2.56s, 1 row(s).

| name | table | type | total_record | valid_record | invalid_record |
|---|---|---|---|---|---|
| sku | channel_order | Foreign Key Constraint | 1085 | 1085 | 0 |

## 19. SHOW DQ: inventory rows failing the committed_within_on_hand rule

```sql
SHOW DQ INVALID RECORD committed_within_on_hand TABLE lightning.metastore.omni_usl.omnialloc.inventory
```

OK in 0.44s, 0 row(s).

| sku | on_hand | committed | unputaway | age_hours |
|---|---|---|---|---|

## 20. Namespace now lists the activated tables

```sql
SHOW NAMESPACES OR TABLES IN lightning.metastore.omni_usl
```

OK in 0.06s, 1 row(s).

| name | type | usl_id | count | activated |
|---|---|---|---|---|
| omnialloc | usl | 1121 | 6 |  |
