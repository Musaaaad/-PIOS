import sys
from pathlib import Path as _Path
ROOT_PATH = _Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path: sys.path.insert(0, str(ROOT_PATH))
from pathlib import Path
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects import postgresql
from app.db.base import Base
from app.models import entities  # noqa: F401

out = Path(__file__).resolve().parents[1] / "sql" / "001_initial_schema.sql"
dialect = postgresql.dialect()
statements = ["-- PIOS MVP PostgreSQL schema v1.4", "CREATE EXTENSION IF NOT EXISTS pgcrypto;"]
for table in Base.metadata.sorted_tables:
    statements.append(str(CreateTable(table).compile(dialect=dialect)).rstrip() + ";")
    for index in table.indexes:
        statements.append(str(CreateIndex(index).compile(dialect=dialect)).rstrip() + ";")
out.write_text("\n\n".join(statements) + "\n", encoding="utf-8")
print(out)
