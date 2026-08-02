from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from app.core.config import get_settings
from app.db.base import Base
from app.models import entities  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        # Alembic's default alembic_version.version_num column is VARCHAR(32).
        # Several of this project's revision ids (e.g. "0012_sprint12_committee_
        # decision_analytics", 42 chars) exceed that width, which makes a fresh
        # `upgrade head` fail with StringDataRightTruncation. Pre-creating the
        # table with a wider column (checkfirst=True downstream in Alembic means
        # it will not try to recreate it) fixes this without renaming any
        # existing revision id or altering any migration file's content.
        connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(255) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        )
        # Commit this DDL on its own transaction. Without this, the implicit
        # transaction SQLAlchemy 2.0 opens on the first exec_driver_sql() call
        # is left uncommitted, and the connection's __exit__ rolls it back
        # silently when the alembic_version table creation is the ONLY change
        # made this run (e.g. `alembic stamp`, which does not otherwise write
        # anything) - Alembic then appears to succeed while persisting nothing.
        connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
