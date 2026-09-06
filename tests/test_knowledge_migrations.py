from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from service_desk.knowledge.migrations import MigrationError, MigrationRunner


class MigrationCursor:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows

    def __enter__(self) -> "MigrationCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, *_: object) -> None:
        return None

    def fetchall(self) -> list[dict[str, str]]:
        return self.rows


class MigrationConnection:
    def __init__(self, rows: list[dict[str, str]] | None = None) -> None:
        self.rows = rows or []
        self.executed: list[tuple[str, object]] = []

    @contextmanager
    def transaction(self) -> Iterator[None]:
        yield

    def execute(self, query: str, params: object = None, **_: object) -> None:
        self.executed.append((query, params))

    def cursor(self, **_: object) -> MigrationCursor:
        return MigrationCursor(self.rows)


def test_migration_runner_applies_frozen_schema_once(tmp_path: Path) -> None:
    migration_file = tmp_path / "001_schema.sql"
    migration_file.write_text("CREATE EXTENSION IF NOT EXISTS vector;", encoding="utf-8")
    connection = MigrationConnection()

    applied = MigrationRunner(connection, tmp_path).apply()  # type: ignore[arg-type]

    assert applied == ("001_schema.sql",)
    assert any("CREATE EXTENSION" in query for query, _ in connection.executed)


def test_migration_runner_rejects_a_changed_applied_migration(tmp_path: Path) -> None:
    migration_file = tmp_path / "001_schema.sql"
    migration_file.write_text("CREATE EXTENSION IF NOT EXISTS vector;", encoding="utf-8")
    runner = MigrationRunner(MigrationConnection(), tmp_path)  # type: ignore[arg-type]
    checksum = runner._discover_migrations()[0].checksum
    migration_file.write_text("CREATE EXTENSION vector;", encoding="utf-8")
    connection = MigrationConnection([{"migration_id": "001_schema.sql", "checksum": checksum}])

    with pytest.raises(MigrationError, match="contents changed"):
        MigrationRunner(connection, tmp_path).apply()  # type: ignore[arg-type]
