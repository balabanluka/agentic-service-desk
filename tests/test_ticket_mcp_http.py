from __future__ import annotations

import os
import socket
import threading
import time

import pytest
import uvicorn

from service_desk.ticketing.mcp import McpTicketGateway, create_ticket_mcp_server
from tests.test_ticket_mcp import FakeTicketBackend


@pytest.mark.mcp
def test_streamable_http_transport_round_trip() -> None:
    if os.getenv("RUN_MCP_TESTS") != "1":
        pytest.skip("set RUN_MCP_TESTS=1 to run the Streamable HTTP integration test")

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = create_ticket_mcp_server(FakeTicketBackend())
    uvicorn_server = uvicorn.Server(
        uvicorn.Config(
            server.streamable_http_app(),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=uvicorn_server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not uvicorn_server.started and time.monotonic() < deadline:
            thread.join(0.02)
        assert uvicorn_server.started

        gateway = McpTicketGateway(f"http://127.0.0.1:{port}/mcp")
        tickets = gateway.list_tickets("cus_orbit_001")
        result = gateway.execute("act_" + "d" * 32, "create_ticket")

        assert tickets[0].subject == "Synthetic MCP test ticket"
        assert result.action_type == "create_ticket"
    finally:
        uvicorn_server.should_exit = True
        thread.join(timeout=5)
        assert not thread.is_alive()
