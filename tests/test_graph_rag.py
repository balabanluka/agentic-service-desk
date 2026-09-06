from __future__ import annotations

import pytest

from service_desk.ai.gateway import ToolCall, WorkflowRequest, WorkflowTurn
from service_desk.data.repository import BusinessRepository
from service_desk.graph.orchestrator import ServiceDeskGraph
from service_desk.knowledge.retrieval import KnowledgeSearchResult
from service_desk.tools.business import BusinessTools
from tests.fakes import FakeModelGateway


def _knowledge_result(*, domain: str) -> KnowledgeSearchResult:
    return KnowledgeSearchResult(
        rank=1,
        chunk_id=f"KB-{domain.upper()}-001--chunk-v1--001",
        chunking_version="v1",
        corpus_version="kb-v1",
        document_id=f"KB-{domain.upper()}-001",
        document_title=f"{domain.title()} guidance",
        domain=domain,
        product="Harborlight Cloud",
        heading_path=("Harborlight guidance",),
        included_heading_paths=(("Harborlight guidance",),),
        chunk_index=1,
        source_path=f"knowledge/{domain}/guidance.md",
        content=f"Synthetic {domain} guidance grounded in the knowledge base.",
        word_count=7,
        content_sha256="a" * 64,
        source_commit="b" * 40,
        cosine_distance=0.1,
        cosine_similarity=0.9,
    )


class FakeKnowledgeRetriever:
    def __init__(
        self, results: tuple[KnowledgeSearchResult, ...] = (), error: Exception | None = None
    ) -> None:
        self.results = results
        self.error = error
        self.calls: list[tuple[str, str | None, int | None]] = []

    def search(
        self, query: str, *, domain: str | None = None, top_k: int | None = None
    ) -> tuple[KnowledgeSearchResult, ...]:
        self.calls.append((query, domain, top_k))
        if self.error is not None:
            raise self.error
        return self.results


@pytest.mark.parametrize(
    ("route", "workflow"),
    [
        ("support", "support_workflow"),
        ("billing", "billing_workflow"),
        ("technical", "technical_workflow"),
    ],
)
def test_each_workflow_receives_only_its_route_scoped_knowledge(
    route: str, workflow: str
) -> None:
    gateway = FakeModelGateway(route=route)
    retriever = FakeKnowledgeRetriever((_knowledge_result(domain=route),))
    graph = ServiceDeskGraph(
        BusinessTools(BusinessRepository.from_default_seed()), gateway, retriever
    )

    result = graph.invoke("cus_orbit_001", "Please help with my request")

    assert retriever.calls == [("Please help with my request", route, None)]
    assert result["transitions"][-1] == workflow
    assert all(request.knowledge_sources for request in gateway.requests)
    assert all(
        request.knowledge_sources[0].document_id == f"KB-{route.upper()}-001"
        for request in gateway.requests
    )
    assert result["knowledge_sources"] == [
        {
            "document_id": f"KB-{route.upper()}-001",
            "document_title": f"{route.title()} guidance",
            "chunk_id": f"KB-{route.upper()}-001--chunk-v1--001",
            "source_path": f"knowledge/{route}/guidance.md",
        }
    ]


class CombinedEvidenceGateway(FakeModelGateway):
    def next_workflow_turn(self, request: WorkflowRequest) -> WorkflowTurn:
        self.requests.append(request)
        if not request.tool_results:
            return WorkflowTurn(tool_calls=(ToolCall(name="list_tickets"),))
        assert request.knowledge_sources
        assert request.tool_results[0].name == "list_tickets"
        return WorkflowTurn(
            answer=(
                "Customer-specific: an existing ticket was found. General guidance: "
                "use the retrieved technical troubleshooting steps."
            )
        )


def test_technical_workflow_combines_scoped_business_facts_and_knowledge() -> None:
    gateway = CombinedEvidenceGateway(route="technical")
    retriever = FakeKnowledgeRetriever((_knowledge_result(domain="technical"),))
    graph = ServiceDeskGraph(
        BusinessTools(BusinessRepository.from_default_seed()), gateway, retriever
    )

    result = graph.invoke(
        "cus_orbit_001", "Our CSV export times out. Do we already have a ticket?"
    )

    assert result["tool_calls"][-1] == {"name": "list_tickets", "status": "success"}
    assert result["answer"].startswith("Customer-specific:")
    assert gateway.requests[-1].tool_results[0].content["items"]
    assert gateway.requests[-1].knowledge_sources[0].document_id == "KB-TECHNICAL-001"


@pytest.mark.parametrize("results,error", [((), None), ((), RuntimeError("database unavailable"))])
def test_workflow_handles_missing_or_unavailable_knowledge_without_inventing_sources(
    results: tuple[KnowledgeSearchResult, ...], error: Exception | None
) -> None:
    gateway = FakeModelGateway(route="support")
    retriever = FakeKnowledgeRetriever(results, error)
    graph = ServiceDeskGraph(
        BusinessTools(BusinessRepository.from_default_seed()), gateway, retriever
    )

    result = graph.invoke("cus_orbit_001", "I need help")

    assert result["answer"].startswith("Offline support answer")
    assert result["knowledge_sources"] == []
    assert all(not request.knowledge_sources for request in gateway.requests)


def test_workflow_drops_knowledge_outside_its_graph_selected_domain() -> None:
    gateway = FakeModelGateway(route="technical")
    retriever = FakeKnowledgeRetriever((_knowledge_result(domain="billing"),))
    graph = ServiceDeskGraph(
        BusinessTools(BusinessRepository.from_default_seed()), gateway, retriever
    )

    result = graph.invoke("cus_orbit_001", "My export is timing out")

    assert retriever.calls == [("My export is timing out", "technical", None)]
    assert result["knowledge_sources"] == []
    assert all(not request.knowledge_sources for request in gateway.requests)


class CrossCustomerInvoiceGateway(FakeModelGateway):
    def next_workflow_turn(self, request: WorkflowRequest) -> WorkflowTurn:
        self.requests.append(request)
        if not request.tool_results:
            return WorkflowTurn(
                tool_calls=(ToolCall(name="get_invoice", arguments={"invoice_id": "inv_willow_2001"}),)
            )
        return WorkflowTurn(answer="I cannot access another customer's invoice.")


def test_retrieval_does_not_relax_cross_customer_invoice_protection() -> None:
    gateway = CrossCustomerInvoiceGateway(route="billing")
    retriever = FakeKnowledgeRetriever((_knowledge_result(domain="billing"),))
    graph = ServiceDeskGraph(
        BusinessTools(BusinessRepository.from_default_seed()), gateway, retriever
    )

    result = graph.invoke("cus_orbit_001", "Show invoice inv_willow_2001")

    assert result["tool_calls"][-1] == {"name": "get_invoice", "status": "denied"}
    assert gateway.requests[-1].tool_results[0].content == {
        "reason": "invoice_not_owned_by_customer"
    }
    assert result["knowledge_sources"][0]["document_id"] == "KB-BILLING-001"
