"""Official MCP server and client boundary for durable ticket operations."""

from __future__ import annotations

import logging
from typing import Any, Protocol

import anyio
from mcp import Client
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from service_desk.domain.models import Ticket
from service_desk.ticketing.models import ActionType, TicketMutationResult
from service_desk.ticketing.repository import TicketActionNotExecutable, TicketRepository


logger = logging.getLogger(__name__)

READ_POLICY = {"effect": "read", "approval_required": False}
WRITE_POLICY = {"effect": "write", "approval_required": True}
_DEFINITIVE_TOOL_ERROR_CODES = frozenset(
    {
        "action_expired",
        "action_not_approved",
        "action_not_found",
        "action_type_mismatch",
        "ticket_not_owned_or_wrong_domain",
    }
)


class TicketMcpError(RuntimeError):
    """Base class for sanitized ticket MCP failures."""


class TicketMcpUnavailable(TicketMcpError):
    """The MCP transport or server was unavailable; outcome may be unknown."""


class TicketMcpToolError(TicketMcpError):
    """The MCP server definitively rejected a ticket operation."""

    def __init__(self, code: str = "mcp_tool_rejected") -> None:
        super().__init__(code)
        self.code = code


class TicketGateway(Protocol):
    def list_tickets(self, customer_id: str) -> tuple[Ticket, ...]: ...

    def get_ticket(self, customer_id: str, ticket_id: str) -> Ticket | None: ...

    def execute(self, action_id: str, action_type: ActionType) -> TicketMutationResult: ...


class TicketMcpBackend(Protocol):
    def list_tickets(self, customer_id: str) -> tuple[Ticket, ...]: ...

    def get_ticket(self, customer_id: str, ticket_id: str) -> Ticket | None: ...

    def execute_action(
        self, action_id: str, expected_type: ActionType
    ) -> TicketMutationResult: ...


class PostgresTicketMcpBackend:
    """Connection-per-call backend suitable for a concurrent MCP service."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def list_tickets(self, customer_id: str) -> tuple[Ticket, ...]:
        return self._with_repository(lambda repository: repository.list_tickets(customer_id))

    def get_ticket(self, customer_id: str, ticket_id: str) -> Ticket | None:
        return self._with_repository(
            lambda repository: repository.get_ticket(customer_id, ticket_id)
        )

    def execute_action(
        self, action_id: str, expected_type: ActionType
    ) -> TicketMutationResult:
        return self._with_repository(
            lambda repository: repository.execute_action(action_id, expected_type)
        )

    def _with_repository(self, callback: Any) -> Any:
        repository = TicketRepository.connect(self._database_url)
        try:
            return callback(repository)
        finally:
            repository.close()


def create_ticket_mcp_server(backend: TicketMcpBackend) -> MCPServer:
    """Build the real MCP tool surface with explicit effect/approval metadata."""

    server = MCPServer(
        "Harborlight Ticketing",
        instructions=(
            "Ticket reads are customer-scoped. Write tools accept only a durable action ID "
            "and execute an already-approved canonical action exactly once."
        ),
        version="3.0.0",
    )

    @server.tool(
        name="tickets_list",
        title="List customer tickets",
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
        meta={"service_desk": READ_POLICY},
    )
    def tickets_list(customer_id: str) -> list[Ticket]:
        """List tickets belonging to one customer workspace."""

        return list(backend.list_tickets(customer_id))

    @server.tool(
        name="ticket_get",
        title="Read customer ticket",
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
        meta={"service_desk": READ_POLICY},
    )
    def ticket_get(customer_id: str, ticket_id: str) -> Ticket | None:
        """Read one ticket only when it belongs to the supplied customer workspace."""

        return backend.get_ticket(customer_id, ticket_id)

    def execute(action_id: str, action_type: ActionType) -> TicketMutationResult:
        try:
            return backend.execute_action(action_id, action_type)
        except TicketActionNotExecutable as error:
            raise ToolError(error.code) from error

    write_annotations = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )

    @server.tool(
        name="ticket_create",
        title="Execute approved ticket creation",
        annotations=write_annotations,
        meta={"service_desk": WRITE_POLICY},
    )
    def ticket_create(action_id: str) -> TicketMutationResult:
        """Execute one approved create-ticket action using its durable identity."""

        return execute(action_id, "create_ticket")

    @server.tool(
        name="ticket_update_status",
        title="Execute approved ticket status update",
        annotations=write_annotations,
        meta={"service_desk": WRITE_POLICY},
    )
    def ticket_update_status(action_id: str) -> TicketMutationResult:
        """Execute one approved status-update action using its durable identity."""

        return execute(action_id, "update_ticket_status")

    @server.tool(
        name="ticket_update_priority",
        title="Execute approved ticket priority update",
        annotations=write_annotations,
        meta={"service_desk": WRITE_POLICY},
    )
    def ticket_update_priority(action_id: str) -> TicketMutationResult:
        """Execute one approved priority-update action using its durable identity."""

        return execute(action_id, "update_ticket_priority")

    return server


class McpTicketGateway:
    """Synchronous application adapter over the official asynchronous MCP client."""

    _WRITE_TOOL_BY_ACTION: dict[ActionType, str] = {
        "create_ticket": "ticket_create",
        "update_ticket_status": "ticket_update_status",
        "update_ticket_priority": "ticket_update_priority",
    }

    def __init__(self, server: str | MCPServer, *, timeout_seconds: float = 10.0) -> None:
        self._server = server
        self._timeout_seconds = timeout_seconds

    def list_tickets(self, customer_id: str) -> tuple[Ticket, ...]:
        payload = self._call("tickets_list", {"customer_id": customer_id})
        items = payload if isinstance(payload, list) else payload.get("result", [])
        return tuple(Ticket.model_validate(item) for item in items)

    def get_ticket(self, customer_id: str, ticket_id: str) -> Ticket | None:
        payload = self._call(
            "ticket_get", {"customer_id": customer_id, "ticket_id": ticket_id}
        )
        value = payload.get("result") if isinstance(payload, dict) and "result" in payload else payload
        return Ticket.model_validate(value) if value is not None else None

    def execute(self, action_id: str, action_type: ActionType) -> TicketMutationResult:
        payload = self._call(self._WRITE_TOOL_BY_ACTION[action_type], {"action_id": action_id})
        return TicketMutationResult.model_validate(payload)

    def _call(self, name: str, arguments: dict[str, object]) -> Any:
        async def invoke() -> Any:
            with anyio.fail_after(self._timeout_seconds):
                async with Client(self._server, raise_exceptions=isinstance(self._server, MCPServer)) as client:
                    result = await client.call_tool(name, arguments)
            if result.is_error:
                code = _definitive_tool_error_code(result.content)
                if code is not None:
                    raise TicketMcpToolError(code)
                raise TicketMcpUnavailable("ticket MCP outcome is unavailable")
            if result.structured_content is None:
                raise TicketMcpUnavailable("ticket MCP response is incomplete")
            return result.structured_content

        try:
            return anyio.run(invoke)
        except TicketMcpToolError:
            raise
        except TicketMcpUnavailable:
            raise
        except Exception as error:
            logger.warning(
                "Ticket MCP request failed [tool=%s, error_type=%s]",
                name,
                type(error).__name__,
            )
            raise TicketMcpUnavailable("ticket MCP service is unavailable") from error


def _definitive_tool_error_code(content: list[Any]) -> str | None:
    """Recognize only the server's allowlisted, safe business rejection codes."""

    for item in content:
        text = getattr(item, "text", None)
        if not isinstance(text, str):
            continue
        candidate = text.rsplit(": ", 1)[-1].strip("'\"")
        if candidate in _DEFINITIVE_TOOL_ERROR_CODES:
            return candidate
    return None
