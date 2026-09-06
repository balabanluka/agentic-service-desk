"""CLI entry point for applying versioned local knowledge-database migrations."""

from pathlib import Path

import psycopg

from service_desk.config import Settings
from service_desk.knowledge.migrations import MigrationRunner


def main() -> None:
    settings = Settings()
    if settings.database_url is None:
        raise SystemExit("DATABASE_URL must be configured before applying migrations")
    connection = psycopg.connect(settings.database_url.get_secret_value())
    try:
        migrations_directory = Path(__file__).with_name("migrations")
        applied = MigrationRunner(connection, migrations_directory).apply()
    finally:
        connection.close()
    print(f"Applied {len(applied)} migration(s): {', '.join(applied) or 'none'}")


if __name__ == "__main__":
    main()
