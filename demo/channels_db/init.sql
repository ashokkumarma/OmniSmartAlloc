-- Channel order database: one table per channel that sells through our own systems.
-- (Amazon orders are NOT here: they come from the Amazon seller REST API.)
CREATE TABLE IF NOT EXISTS dtc_orders (
    id                TEXT PRIMARY KEY,
    ts                TEXT NOT NULL,
    sku               TEXT NOT NULL,
    qty               INTEGER NOT NULL CHECK (qty > 0),
    fulfilled_qty     INTEGER NOT NULL DEFAULT 0,
    status            TEXT NOT NULL,
    partial_shipments TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS etsy_orders    (LIKE dtc_orders INCLUDING ALL);
CREATE TABLE IF NOT EXISTS walmart_orders (LIKE dtc_orders INCLUDING ALL);
