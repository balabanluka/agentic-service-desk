"""FastAPI application factory for Agentic Service Desk V1."""

from fastapi import FastAPI

from service_desk.ai.gateway import ModelGateway, ModelGatewayError
from service_desk.ai.openai_gateway import OpenAIModelGateway
from service_desk.api.routes import create_router
from service_desk.config import Settings
from service_desk.data.repository import BusinessRepository
from service_desk.graph.orchestrator import ServiceDeskGraph
from service_desk.knowledge.embeddings import OpenAIEmbeddingClient
from service_desk.knowledge.retrieval import DatabaseKnowledgeRetriever, KnowledgeSearchProvider
from service_desk.services.chat import ChatService
from service_desk.tools.business import BusinessTools


class UnavailableModelGateway:
    """Allows health checks without credentials while rejecting live chat safely."""

    def route(self, message: str):
        raise ModelGatewayError("OPENAI_API_KEY is not configured")

    def next_workflow_turn(self, request):
        raise ModelGatewayError("OPENAI_API_KEY is not configured")


def create_app(
    *,
    model_gateway: ModelGateway | None = None,
    repository: BusinessRepository | None = None,
    settings: Settings | None = None,
    knowledge_retriever: KnowledgeSearchProvider | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings()
    api_key = resolved_settings.openai_api_key
    uses_default_model_gateway = model_gateway is None
    if uses_default_model_gateway:
        model_gateway = (
            OpenAIModelGateway(api_key.get_secret_value(), resolved_settings.openai_model)
            if api_key is not None
            else UnavailableModelGateway()
        )
    if (
        knowledge_retriever is None
        and uses_default_model_gateway
        and api_key is not None
        and resolved_settings.database_url is not None
    ):
        knowledge_retriever = DatabaseKnowledgeRetriever(
            database_url=resolved_settings.database_url.get_secret_value(),
            embedding_client=OpenAIEmbeddingClient(api_key.get_secret_value()),
            embedding_model=resolved_settings.openai_embedding_model,
            embedding_dimensions=resolved_settings.openai_embedding_dimensions,
            corpus_version=resolved_settings.knowledge_corpus_version,
            default_top_k=resolved_settings.knowledge_default_top_k,
        )

    business_tools = BusinessTools(repository or BusinessRepository.from_default_seed())
    chat_service = ChatService(ServiceDeskGraph(business_tools, model_gateway, knowledge_retriever))

    app = FastAPI(title="Agentic Service Desk", version="0.1.0")
    app.include_router(create_router(chat_service))
    return app


app = create_app()
