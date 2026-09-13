"""HTTP routes for the V1 service desk."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from service_desk.ai.gateway import ModelGatewayError
from service_desk.api.schemas import (
    ActionDecisionRequest,
    ActionResponse,
    AuditEventResponse,
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    HealthResponse,
)
from service_desk.services.chat import ChatService, CustomerNotFoundError
from service_desk.ticketing.actions import (
    ActionExecutionUnavailable,
    ActionNotFoundError,
    ActionService,
)
from service_desk.ticketing.models import TicketAction


def create_router(chat_service: ChatService, action_service: ActionService | None = None) -> APIRouter:
    router = APIRouter()

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @router.post(
        "/api/chat",
        response_model=ChatResponse,
        responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    def chat(request: ChatRequest) -> ChatResponse | JSONResponse:
        try:
            result = chat_service.chat(request.customer_id, request.message)
        except CustomerNotFoundError:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    detail="Customer account was not found.", code="customer_not_found"
                ).model_dump(),
                headers={"X-Error-Code": "customer_not_found"},
            )
        except ModelGatewayError:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=ErrorResponse(
                    detail="The AI service is temporarily unavailable.", code="model_unavailable"
                ).model_dump(),
                headers={"X-Error-Code": "model_unavailable"},
            )
        return ChatResponse(answer=result.answer, execution=result.execution)

    @router.get(
        "/api/actions/{action_id}",
        response_model=ActionResponse,
        responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    def get_action(action_id: str, customer_id: str) -> ActionResponse | JSONResponse:
        if action_service is None:
            return _action_service_unavailable()
        try:
            action = action_service.get(action_id, customer_id)
            events = action_service.audit(action_id, customer_id)
        except ActionNotFoundError:
            return _action_not_found()
        return _action_response(action, events=events)

    @router.post(
        "/api/actions/{action_id}/approve",
        response_model=ActionResponse,
        responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    def approve_action(
        action_id: str, request: ActionDecisionRequest
    ) -> ActionResponse | JSONResponse:
        if action_service is None:
            return _action_service_unavailable()
        try:
            action = action_service.approve(action_id, request.customer_id)
        except ActionNotFoundError:
            return _action_not_found()
        except ActionExecutionUnavailable:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=ErrorResponse(
                    detail="The approved action could not be completed yet; retry is safe.",
                    code="action_execution_unavailable",
                ).model_dump(),
                headers={"X-Error-Code": "action_execution_unavailable"},
            )
        return _action_response(action)

    @router.post(
        "/api/actions/{action_id}/reject",
        response_model=ActionResponse,
        responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    def reject_action(
        action_id: str, request: ActionDecisionRequest
    ) -> ActionResponse | JSONResponse:
        if action_service is None:
            return _action_service_unavailable()
        try:
            action = action_service.reject(action_id, request.customer_id)
        except ActionNotFoundError:
            return _action_not_found()
        return _action_response(action)

    return router


def _action_response(action: TicketAction, *, events: tuple = ()) -> ActionResponse:
    return ActionResponse(
        action_id=action.action_id,
        customer_id=action.customer_id,
        route=action.route,
        action_type=action.action_type,
        payload=action.payload,
        status=action.status,
        approval_required=action.approval_required,
        expires_at=action.expires_at.isoformat(),
        result=action.result,
        error_code=action.error_code,
        audit_events=[
            AuditEventResponse(
                event_id=event.event_id,
                event_type=event.event_type,
                actor_type=event.actor_type,
                metadata=event.metadata,
                created_at=event.created_at.isoformat(),
            )
            for event in events
        ],
    )


def _action_not_found() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=ErrorResponse(
            detail="Action was not found for this customer.", code="action_not_found"
        ).model_dump(),
        headers={"X-Error-Code": "action_not_found"},
    )


def _action_service_unavailable() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=ErrorResponse(
            detail="The action service is not configured.", code="action_service_unavailable"
        ).model_dump(),
        headers={"X-Error-Code": "action_service_unavailable"},
    )
