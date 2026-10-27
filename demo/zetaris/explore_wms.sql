-- Exploratory queries: WMS (two Lightning REST tables: inventory_raw and inbound_raw).

-- @title WMS: REST tables in the Lightning database
SHOW LIGHTNING TABLES WMS;

-- @title WMS: on-hand, committed and free stock per SKU
SELECT i.sku, i.on_hand, i.committed, i.unputaway, i.age_hours, i.on_hand - i.committed AS free_units
FROM WMS.inventory_raw LATERAL VIEW explode(inventory) AS i
ORDER BY i.sku;

-- @title WMS: inbound purchase-order lines per SKU and status
SELECT s.sku, s.status, COUNT(*) AS po_lines, SUM(s.qty) AS units, MIN(s.eta_days) AS soonest_eta_days
FROM WMS.inbound_raw LATERAL VIEW explode(inbound) AS s
GROUP BY s.sku, s.status
ORDER BY s.sku, s.status;
