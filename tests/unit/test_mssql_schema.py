"""The schema as MS SQL would get it (M20 review, no server needed): Unicode text everywhere, no
cascading deletes (MS SQL refuses multiple cascade paths), filtered unique indexes keep their
WHERE, and reserved words such as KEY are quoted."""

import pytest
from sqlalchemy import Enum, Index, String, Table
from sqlalchemy.dialects import mssql
from sqlalchemy.schema import CreateIndex, CreateTable

import taskboard.db.models  # noqa: F401  (registers every table)
from taskboard.db.base import Base

DIALECT = mssql.dialect()
TABLES = sorted(Base.metadata.tables.values(), key=lambda t: t.name)


@pytest.mark.parametrize("table", TABLES, ids=[t.name for t in TABLES])
def test_a_table_as_ms_sql_creates_it(table: Table) -> None:
    ddl = str(CreateTable(table).compile(dialect=DIALECT))
    assert "CASCADE" not in ddl.upper()
    for column in table.columns:
        if isinstance(column.type, String) and not isinstance(column.type, Enum):
            rendered = column.type.compile(dialect=DIALECT)
            assert rendered.startswith("NVARCHAR"), f"{table.name}.{column.name} is {rendered}"
    if "key" in table.columns:
        assert "[key]" in ddl


FILTERED = [
    (table, index)
    for table in TABLES
    for index in table.indexes
    if isinstance(index, Index) and index.dialect_options["sqlite"].get("where") is not None
]


@pytest.mark.parametrize(("table", "index"), FILTERED, ids=[i.name or "" for _, i in FILTERED])
def test_filtered_indexes_stay_filtered(table: Table, index: Index) -> None:
    assert FILTERED, "the schema has filtered unique indexes (one root per map, ...)"
    assert " WHERE " in str(CreateIndex(index).compile(dialect=DIALECT)), (
        f"{index.name} on {table.name} needs `mssql_where` too"
    )
