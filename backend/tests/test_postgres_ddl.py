from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from app.db.base import Base
from app.models import entities  # noqa: F401


def test_all_tables_compile_for_postgresql():
    dialect = postgresql.dialect()
    statements = [str(CreateTable(t).compile(dialect=dialect)) for t in Base.metadata.sorted_tables]
    assert len(statements) == 92
    joined = "\n".join(statements)
    assert "measurable_elements" in joined
    assert "evidence_items" in joined
    assert "audit_events" in joined
    assert "readiness_snapshot_items" in joined
    assert "effectiveness_checks" in joined
    assert "assurance_programs" in joined
    assert "data_quality_issues" in joined
    assert "rollout_wave_sites" in joined
    assert "release_packages" in joined
    assert "audit_export_packages" in joined
