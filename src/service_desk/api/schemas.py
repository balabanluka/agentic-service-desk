"""Public API schemas."""

from pydantic import BaseModel, Field

from service_desk.services.chat import ExecutionMetadata


class HealthResponse(BaseModel):
    status: str


class ChatRequest(BaseModel):
    customer_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=4_000)


class ChatResponse(BaseModel):
    answer: str
    execution: ExecutionMetadata


class ErrorResponse(BaseModel):
    detail: str
    code: str
