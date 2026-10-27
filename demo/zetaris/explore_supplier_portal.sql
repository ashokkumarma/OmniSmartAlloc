-- Exploratory queries: SUPPLIER_PORTAL (Lightning REST table of supplier reliability history).

-- @title SUPPLIER_PORTAL: column types Zetaris froze for the raw REST table
DESCRIBE SUPPLIER_PORTAL.reliability_raw;

-- @title SUPPLIER_PORTAL: suppliers ranked by on-time rate
SELECT r.supplier, r.on_time_rate, r.typical_delay_days
FROM SUPPLIER_PORTAL.reliability_raw LATERAL VIEW explode(suppliers) AS r
ORDER BY r.on_time_rate DESC;

-- @title SUPPLIER_PORTAL x WMS: inbound units at risk, weighted by supplier lateness (cross-source join)
-- Both sides are flattened in subqueries first: the same join written with LATERAL VIEW directly on the
-- left-hand table was rejected by the Lightning parser with "mismatched input 's' expecting 'METADATA'".
SELECT w.supplier, r.on_time_rate, SUM(w.qty) AS inbound_units,
       ROUND(SUM(w.qty) * (1 - r.on_time_rate), 1) AS units_likely_late
FROM (SELECT s.supplier, s.qty FROM WMS.inbound_raw LATERAL VIEW explode(inbound) AS s) w
JOIN (SELECT x.supplier, x.on_time_rate FROM SUPPLIER_PORTAL.reliability_raw LATERAL VIEW explode(suppliers) AS x) r
  ON r.supplier = w.supplier
GROUP BY w.supplier, r.on_time_rate
ORDER BY units_likely_late DESC;
