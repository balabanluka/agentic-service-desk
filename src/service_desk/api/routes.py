"""HTTP routes for the V1 service desk."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from service_desk.ai.gateway import ModelGatewayError
from service_desk.api.schemas import ChatRequest, ChatResponse, ErrorResponse, HealthResponse
from service_desk.services.chat import ChatService, CustomerNotFoundError


def create_router(chat_service: ChatService) -> APIRouter:
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
        except CustomerNotFoundError as exc:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    detail="Customer account was not found.", code="customer_not_found"
                ).model_dump(),
                headers={"X-Error-Code": "customer_not_found"},
            )
        except ModelGatewayError as exc:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=ErrorResponse(
                    detail="The AI service is temporarily unavailable.", code="model_unavailable"
                ).model_dump(),
                headers={"X-Error-Code": "model_unavailable"},
            )
        return ChatResponse(answer=result.answer, execution=result.execution)

    return router
