from pathlib import Path
import re

from models import Base


def test_mysql_baseline_matches_orm_tables_and_column_names():
    schema = (Path(__file__).resolve().parents[1] / "memoir-mysql-schema.sql").read_text()
    tables = dict(re.findall(r"^CREATE TABLE(?: IF NOT EXISTS)? `(\w+)`\s*\((.*?)\) ENGINE", schema, re.M | re.S))
    assert tables.keys() == Base.metadata.tables.keys()
    for name, table in Base.metadata.tables.items():
        assert set(table.columns.keys()) == set(re.findall(r"^  `(\w+)` ", tables[name], re.M)), name
