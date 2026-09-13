from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from service_desk.config import Settings
from service_desk.knowledge.migrations import MigrationRunner


@pytest.mark.postgres
def test_clean_database_and_v2_upgrade_apply_ordered_v3_migration(tmp_path: Path) -> None:
    if os.getenv("RUN_POSTGRES_TESTS") != "1":
        pytest.skip("set RUN_POSTGRES_TESTS=1 to run local PostgreSQL integration tests")
    settings = Settings()
    if settings.database_url is None:
        pytest.skip("DATABASE_URL is not configured")

    configured_url = settings.database_url.get_secret_value()
    parameters = conninfo_to_dict(configured_url)
    database_name = f"asd_v3_migration_{uuid4().hex[:12]}"
    admin_url = make_conninfo(**{**parameters, "dbname": "postgres"})
    test_url = make_conninfo(**{**parameters, "dbname": database_name})
    admin = psycopg.connect(admin_url, autocommit=True)
    created = False
    try:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
        created = True
        migrations = Path(__file__).resolve().parents[1] / "src/service_desk/knowledge/migrations"
        v2_only = tmp_path / "v2-migrations"
        v2_only.mkdir()
        source_v2 = migrations / "001_knowledge_schema.sql"
        (v2_only / source_v2.name).write_bytes(source_v2.read_bytes())

        connection = psycopg.connect(test_url)
        try:
            assert MigrationRunner(connection, v2_only).apply() == (
                "001_knowledge_schema.sql",
            )
            assert MigrationRunner(connection, migrations).apply() == (
                "002_ticket_actions.sql",
            )
            assert MigrationRunner(connection, migrations).apply() == ()
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                ).fetchall()
            }
            extension = connection.execute(
                "SELECT extname FROM pg_extension WHERE extname='vector'"
            ).fetchone()
        finally:
            connection.close()

        assert extension == ("vector",)
        assert {
            "knowledge_chunks",
            "knowledge_embeddings",
            "tickets",
            "ticket_actions",
            "ticket_action_receipts",
            "ticket_action_audit_events",
        }.issubset(tables)
    finally:
        if created:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s",
                (database_name,),
            )
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
        admin.close()
