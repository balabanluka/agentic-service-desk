"""Versioned SQL migration support for the local knowledge database."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


@dataclass(frozen=True, slots=True)
class AppliedMigration:
    migration_id: str
    checksum: str


class MigrationError(RuntimeError):
    """Raised when a versioned knowledge-database migration is unsafe to apply."""


class MigrationRunner:
    """Applies immutable, ordered SQL migrations exactly once per database."""

    def __init__(self, connection: psycopg.Connection[Any], migrations_directory: Path) -> None:
        self._connection = connection
        self._migrations_directory = migrations_directory

    def apply(self) -> tuple[str, ...]:
        migrations = self._discover_migrations()
        applied_ids: list[str] = []
        with self._connection.transaction():
            self._ensure_migration_table()
            existing = self._existing_migrations()
            for migration in migrations:
                prior_checksum = existing.get(migration.migration_id)
                if prior_checksum is not None:
                    if prior_checksum != migration.checksum:
                        raise MigrationError(
                            f"migration contents changed after application: {migration.migration_id}"
                        )
                    continue
                self._connection.execute(migration.sql, prepare=False)
                self._connection.execute(
                    "INSERT INTO schema_migrations (migration_id, checksum) VALUES (%s, %s)",
                    (migration.migration_id, migration.checksum),
                )
                applied_ids.append(migration.migration_id)
        return tuple(applied_ids)

    def _discover_migrations(self) -> tuple["_Migration", ...]:
        if not self._migrations_directory.is_dir():
            raise MigrationError(f"migration directory does not exist: {self._migrations_directory}")
        migrations = tuple(
            _Migration.from_file(path)
            for path in sorted(self._migrations_directory.glob("[0-9][0-9][0-9]_*.sql"))
        )
        if not migrations:
            raise MigrationError("no SQL migrations were found")
        migration_ids = [migration.migration_id for migration in migrations]
        if len(migration_ids) != len(set(migration_ids)):
            raise MigrationError("migration IDs must be unique")
        return migrations

    def _ensure_migration_table(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_id text PRIMARY KEY,
                checksum char(64) NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )

    def _existing_migrations(self) -> dict[str, str]:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT migration_id, checksum FROM schema_migrations")
            return {str(row["migration_id"]): str(row["checksum"]) for row in cursor.fetchall()}


@dataclass(frozen=True, slots=True)
class _Migration:
    migration_id: str
    checksum: str
    sql: str

    @classmethod
    def from_file(cls, path: Path) -> "_Migration":
        sql = path.read_text(encoding="utf-8")
        return cls(
            migration_id=path.name,
            checksum=sha256(sql.encode("utf-8")).hexdigest(),
            sql=sql,
        )
