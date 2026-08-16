from sqlalchemy import create_engine, text

from app.database.migrate import run_migrations


def test_migration_runner_applies_each_file_once(tmp_path):
    (tmp_path / "001_create_sample.sql").write_text(
        "CREATE TABLE sample (id INTEGER PRIMARY KEY); CREATE INDEX ix_sample_id ON sample(id);",
        encoding="utf-8",
    )
    (tmp_path / "002_insert_sample.sql").write_text(
        "INSERT INTO sample (id) VALUES (1)", encoding="utf-8"
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")

    first = run_migrations(engine, tmp_path)
    second = run_migrations(engine, tmp_path)

    versions = (
        engine.connect()
        .execute(text("SELECT version FROM schema_migrations ORDER BY version"))
        .scalars()
        .all()
    )
    count = engine.connect().execute(text("SELECT COUNT(*) FROM sample")).scalar_one()
    assert first == ["001_create_sample", "002_insert_sample"]
    assert second == []
    assert versions == ["001_create_sample", "002_insert_sample"]
    assert count == 1
