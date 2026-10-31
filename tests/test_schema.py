from pathlib import Path
import re

from models import Base


def test_mysql_baseline_matches_orm_tables_and_column_names():
    schema = (Path(__file__).resolve().parents[1] / "memoir-mysql-schema.sql").read_text()
    tables = dict(re.findall(r"^CREATE TABLE(?: IF NOT EXISTS)? `(\w+)`\s*\((.*?)\) ENGINE", schema, re.M | re.S))
    assert tables.keys() == Base.metadata.tables.keys()
    for name, table in Base.metadata.tables.items():
        assert set(table.columns.keys()) == set(re.findall(r"^  `(\w+)` ", tables[name], re.M)), name


def test_unreleased_inapp_migrations_quote_mysql_reserved_columns():
    from sqlalchemy.dialects.mysql import dialect
    from migrate import _split_statements
    preparer=dialect().identifier_preparer
    root=Path(__file__).resolve().parents[1]
    for path in (root/'migrations').glob('*.sql'):
        if int(path.name[:3])<16:continue
        for statement in _split_statements(path.read_text()):
            if not statement.lstrip().upper().startswith('CREATE TABLE'):continue
            for match in re.finditer(r'(?:\(|,)\s*([`"]?)(\w+)\1\s+(?:varchar|integer|int|mediumtext|text|json|boolean|datetime)\b',statement,re.I):
                quote,name=match.groups()
                assert not preparer._requires_quotes(name) or quote=='`',(path.name,name)
