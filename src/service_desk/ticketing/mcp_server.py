"""CLI for the localhost-only Harborlight ticket MCP service."""

from service_desk.config import Settings
from service_desk.ticketing.mcp import PostgresTicketMcpBackend, create_ticket_mcp_server


def main() -> None:
    settings = Settings()
    if settings.database_url is None:
        raise SystemExit("DATABASE_URL must be configured before starting the ticket MCP server")
    server = create_ticket_mcp_server(
        PostgresTicketMcpBackend(settings.database_url.get_secret_value())
    )
    server.run(transport="streamable-http", host="127.0.0.1", port=8001)


if __name__ == "__main__":
    main()
