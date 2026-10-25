import pytest

from src.data_connectors.readonly import ReadOnlyViolation, ensure_read_only


@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "select * from NY_TAXI.taxi_zones limit 5;",
    "SHOW LIGHTNING DATABASES",
    "DESCRIBE DATASOURCE TABLE crm_pg.customers",
    "WITH x AS (SELECT 1 AS a) SELECT a FROM x",
    "SELECT 'drop table; delete' AS note",
    "SELECT replace(name, 'a', 'b') FROM crm_pg.customers",
])
def test_allows_read_only(sql):
    assert ensure_read_only(sql)


@pytest.mark.parametrize("sql", [
    "", "DROP TABLE t", "CREATE LIGHTNING DATABASE x", "SELECT 1; DROP TABLE t",
    "WITH x AS (SELECT 1) INSERT INTO t SELECT * FROM x", "GRANT ALL ON t TO bob",
    "/* hi */ DELETE FROM t", "CACHE DATASOURCE TABLE a.b",
])
def test_blocks_writes_and_multi_statements(sql):
    with pytest.raises(ReadOnlyViolation):
        ensure_read_only(sql)
