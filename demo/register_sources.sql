-- OmniSmartAlloc demo: register the fragmented systems in Zetaris (WRITES to the instance).
-- Run with: python scripts/register_demo_sources.py --execute

CREATE LIGHTNING DATABASE WMS DESCRIBE BY "Warehouse-inventory-and-inbound-shipments";
CREATE LIGHTNING REST TABLE inventory_raw FROM WMS REQUEST(
    endpoint "http://host.docker.internal:8901/api/wms/inventory",
    method "get", response_type "json", http_encoding "URLENCODED"
) HEADER (user-agent "omnismartalloc hackathon@local.dev") BODY ();
CREATE LIGHTNING REST TABLE inbound_raw FROM WMS REQUEST(
    endpoint "http://host.docker.internal:8901/api/wms/inbound",
    method "get", response_type "json", http_encoding "URLENCODED"
) HEADER (user-agent "omnismartalloc hackathon@local.dev") BODY ();

CREATE LIGHTNING DATABASE SUPPLIER_PORTAL DESCRIBE BY "Supplier-and-carrier-reliability-history";
CREATE LIGHTNING REST TABLE reliability_raw FROM SUPPLIER_PORTAL REQUEST(
    endpoint "http://host.docker.internal:8901/api/suppliers/reliability",
    method "get", response_type "json", http_encoding "URLENCODED"
) HEADER (user-agent "omnismartalloc hackathon@local.dev") BODY ();

CREATE LIGHTNING DATABASE CHANNEL_ANALYTICS DESCRIBE BY "Channel-margin,-velocity-and-demand-confidence";
CREATE LIGHTNING REST TABLE economics_raw FROM CHANNEL_ANALYTICS REQUEST(
    endpoint "http://host.docker.internal:8901/api/channels/economics",
    method "get", response_type "json", http_encoding "URLENCODED"
) HEADER (user-agent "omnismartalloc hackathon@local.dev") BODY ();

CREATE LIGHTNING DATABASE RULES_ENGINE DESCRIBE BY "Business-rules-locks,-overrides,-clearance,-promotions";
CREATE LIGHTNING REST TABLE rules_raw FROM RULES_ENGINE REQUEST(
    endpoint "http://host.docker.internal:8901/api/rules/skus",
    method "get", response_type "json", http_encoding "URLENCODED"
) HEADER (user-agent "omnismartalloc hackathon@local.dev") BODY ();

CREATE SCHEMASTORE CONTAINER omnismart;

CREATE SCHEMASTORE VIEW wms_inventory WITH CONTAINER omnismart AS
SELECT i.sku, i.on_hand, i.committed, i.unputaway, i.age_hours
FROM WMS.inventory_raw LATERAL VIEW explode(inventory) AS i;

CREATE SCHEMASTORE VIEW wms_inbound WITH CONTAINER omnismart AS
SELECT s.po, s.sku, s.qty, s.eta_days, s.status, s.supplier
FROM WMS.inbound_raw LATERAL VIEW explode(inbound) AS s;

CREATE SCHEMASTORE VIEW supplier_reliability WITH CONTAINER omnismart AS
SELECT r.supplier, r.on_time_rate, r.typical_delay_days
FROM SUPPLIER_PORTAL.reliability_raw LATERAL VIEW explode(suppliers) AS r;

CREATE SCHEMASTORE VIEW channel_economics WITH CONTAINER omnismart AS
SELECT e.sku, e.channel, e.unit_margin, e.demand_confidence, e.v7, e.v30, e.v90, e.trend, e.floor_units, e.margin_age_hours
FROM CHANNEL_ANALYTICS.economics_raw LATERAL VIEW explode(economics) AS e;

CREATE SCHEMASTORE VIEW sku_rules WITH CONTAINER omnismart AS
SELECT r.sku, r.locked, r.manual_override, r.clearance, r.promo_multiplier
FROM RULES_ENGINE.rules_raw LATERAL VIEW explode(rules) AS r;
