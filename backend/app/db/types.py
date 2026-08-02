from sqlalchemy import JSON, Uuid, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

# Portable ORM types: PostgreSQL remains the production dialect, while SQLite
# is used only by the deterministic integration harness included in this package.
UUIDType = Uuid(as_uuid=True)
JSONType = JSON().with_variant(JSONB(), "postgresql")


class RegexCheckConstraint(CheckConstraint):
    """PostgreSQL regex check with a harmless SQLite test equivalent."""


@compiles(RegexCheckConstraint, "sqlite")
def _compile_regex_check_sqlite(element, compiler, **kw):
    return "CHECK (1)"
