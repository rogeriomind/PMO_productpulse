from pathlib import Path

from sqlalchemy import Engine, create_engine, text

from app.config import get_settings
from app.database.connection import normalize_database_url

MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def run_migrations(
    engine: Engine | None = None, migrations_dir: Path = MIGRATIONS_DIR
) -> list[str]:
    owned_engine = engine is None
    if engine is None:
        settings = get_settings()
        engine = create_engine(
            normalize_database_url(settings.database_url), pool_pre_ping=True
        )

    applied: list[str] = []
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                  version VARCHAR(255) PRIMARY KEY,
                  applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        existing = set(
            connection.execute(text("SELECT version FROM schema_migrations"))
            .scalars()
            .all()
        )
        for path in sorted(migrations_dir.glob("*.sql")):
            version = path.stem
            if version in existing:
                continue
            for statement in _split_sql(path.read_text(encoding="utf-8")):
                connection.exec_driver_sql(statement)
            inserted = _record_migration(connection, version)
            if inserted:
                applied.append(version)

    if owned_engine:
        engine.dispose()
    return applied


def _split_sql(sql: str) -> list[str]:
    return [statement.strip() for statement in sql.split(";") if statement.strip()]


def _record_migration(connection, version: str) -> bool:
    if connection.dialect.name == "postgresql":
        result = connection.execute(
            text(
                """
                INSERT INTO schema_migrations (version)
                VALUES (:version)
                ON CONFLICT (version) DO NOTHING
                """
            ),
            {"version": version},
        )
        return bool(result.rowcount)

    if connection.dialect.name == "sqlite":
        result = connection.execute(
            text("INSERT OR IGNORE INTO schema_migrations (version) VALUES (:version)"),
            {"version": version},
        )
        return bool(result.rowcount)

    try:
        connection.execute(
            text("INSERT INTO schema_migrations (version) VALUES (:version)"),
            {"version": version},
        )
        return True
    except Exception:
        return False


if __name__ == "__main__":
    versions = run_migrations()
    print({"applied": versions})
