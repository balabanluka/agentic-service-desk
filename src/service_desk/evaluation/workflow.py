"""Deterministic workflow-contract evaluation and live-review report helpers."""

from __future__ import annotations

from collections.abc import Callable

from service_desk.ai.gateway import ModelGatewayError, RouteDecision, ToolCall, WorkflowRequest, WorkflowTurn
from service_desk.data.repository import BusinessRepository
from service_desk.evaluation.models import ToolFactExpectation, WorkflowCase, WorkflowDataset
from service_desk.graph.orchestrator import ServiceDeskGraph
from service_desk.graph.state import AgentState
from service_desk.knowledge.retrieval import KnowledgeSearchResult
from service_desk.tools.business import BusinessTools


class OfflineEvaluationModelGateway:
    """Deterministically drives one case through the real controlled graph."""

    def __init__(self, case: WorkflowCase) -> None:
        self._case = case
        self._turn_index = 0

    def route(self, message: str) -> RouteDecision:
        del message
        if self._case.needs_clarification:
            return RouteDecision(needs_clarification=True, rationale="Evaluation clarification.")
        return RouteDecision(
            route=self._case.expected_route,  # type: ignore[arg-type]
            needs_clarification=False,
            rationale="Evaluation-selected route.",
        )

    def next_workflow_turn(self, request: WorkflowRequest) -> WorkflowTurn:
        del request
        if self._turn_index < len(self._case.planned_tool_calls):
            planned = self._case.planned_tool_calls[self._turn_index]
            self._turn_index += 1
            return WorkflowTurn(tool_calls=(ToolCall(name=planned.name, arguments=planned.arguments),))
        return WorkflowTurn(answer="Offline evaluation answer; review live answers separately.")


class OfflineEvaluationRetriever:
    """A deterministic source provider for graph-contract checks, not retrieval scoring."""

    def __init__(self, case: WorkflowCase) -> None:
        self._case = case

    def search(
        self, query: str, *, domain: str | None = None, top_k: int | None = None
    ) -> tuple[KnowledgeSearchResult, ...]:
        del query, top_k
        if domain is None or self._case.needs_clarification:
            return ()
        return tuple(
            KnowledgeSearchResult(
                rank=index,
                chunk_id=f"{document_id}--chunk-v1--001",
                chunking_version="v1",
                corpus_version="kb-v1",
                document_id=document_id,
                document_title=f"Evaluation source {document_id}",
                domain=domain,
                product="Harborlight Cloud",
                heading_path=("Evaluation source",),
                included_heading_paths=(("Evaluation source",),),
                chunk_index=1,
                source_path=f"evaluation://{document_id}",
                content=f"Synthetic evaluation context for {document_id}.",
                word_count=5,
                content_sha256="0" * 64,
                source_commit="0" * 40,
                cosine_distance=0.0,
                cosine_similarity=1.0,
            )
            for index, document_id in enumerate(self._case.expected_knowledge_document_ids, start=1)
        )


def run_offline_workflow_evaluation(
    dataset: WorkflowDataset, *, dataset_path_fingerprint: str
) -> dict[str, object]:
    """Evaluate graph contracts with deterministic model and retrieval doubles only."""

    def invoke(case: WorkflowCase) -> AgentState:
        graph = ServiceDeskGraph(
            BusinessTools(BusinessRepository.from_default_seed()),
            OfflineEvaluationModelGateway(case),
            OfflineEvaluationRetriever(case),
        )
        return graph.invoke(case.customer_id, case.message, request_id=f"evaluation-{case.case_id}")

    return evaluate_workflows(
        dataset,
        dataset_path_fingerprint=dataset_path_fingerprint,
        invoke_case=invoke,
        mode="offline",
    )


def evaluate_workflows(
    dataset: WorkflowDataset,
    *,
    dataset_path_fingerprint: str,
    invoke_case: Callable[[WorkflowCase], AgentState],
    mode: str,
    limit: int | None = None,
) -> dict[str, object]:
    """Evaluate deterministic graph metadata; live answers remain human-review artifacts."""

    selected_cases = dataset.cases if limit is None else dataset.cases[:limit]
    reports = [_evaluate_case(case, invoke_case, mode) for case in selected_cases]
    passed = [report for report in reports if report["passed"]]
    return {
        "evaluation_type": "grounded_workflow",
        "mode": mode,
        "dataset_id": dataset.dataset_id,
        "dataset_version": dataset.dataset_version,
        "dataset_fingerprint": dataset_path_fingerprint,
        "corpus_version": dataset.corpus_version,
        "chunking_version": dataset.chunking_version,
        "embedding_model": dataset.embedding_model,
        "case_count": len(reports),
        "passed_case_rate": _rate(len(passed), len(reports)),
        "route_accuracy": _mean_check(reports, "route_matches"),
        "clarification_accuracy": _mean_check(reports, "clarification_matches"),
        "required_tool_rate": _mean_check(reports, "required_tools_present"),
        "knowledge_source_coverage": _mean_check(reports, "knowledge_sources_present"),
        "safety_rate": _mean_check(reports, "safety_expectation_met", ignore_missing=True),
        "cases": reports,
        "manual_answer_review_required": mode == "live-rag",
    }


def _evaluate_case(
    case: WorkflowCase, invoke_case: Callable[[WorkflowCase], AgentState], mode: str
) -> dict[str, object]:
    try:
        state = invoke_case(case)
    except ModelGatewayError as error:
        blocked = "outside the allowlist" in str(error)
        checks = {
            "route_matches": case.safety_expectation == "forbidden_tool_blocked" and blocked,
            "clarification_matches": True,
            "required_tools_present": True,
            "allowed_tools_only": blocked,
            "tool_statuses_match": True,
            "customer_facts_grounded": True,
            "knowledge_sources_present": True,
            "safety_expectation_met": case.safety_expectation == "forbidden_tool_blocked" and blocked,
        }
        return {
            "case_id": case.case_id,
            "checks": checks,
            "passed": all(checks.values()),
            "workflow_tools": [],
            "knowledge_document_ids": [],
            "error": type(error).__name__,
            "answer": None,
        }

    workflow_records = state["tool_calls"][1:]
    workflow_tools = [record["name"] for record in workflow_records]
    source_document_ids = [source["document_id"] for source in state.get("knowledge_sources", [])]
    observed_statuses = {record["name"]: record["status"] for record in workflow_records}
    checks = {
        "route_matches": state.get("selected_route") == case.expected_route,
        "clarification_matches": bool(state.get("needs_clarification")) == case.needs_clarification,
        "required_tools_present": set(case.required_tools).issubset(workflow_tools),
        "allowed_tools_only": set(workflow_tools).issubset(case.allowed_tools),
        "tool_statuses_match": all(
            observed_statuses.get(tool_name) == expected_status
            for tool_name, expected_status in case.expected_tool_statuses.items()
        ),
        "customer_facts_grounded": all(
            _fact_matches(expectation, state) for expectation in case.required_customer_facts
        ),
        "knowledge_sources_present": set(case.expected_knowledge_document_ids).issubset(
            source_document_ids
        ),
        "safety_expectation_met": _safety_matches(case, observed_statuses),
    }
    evaluated_checks = [value for value in checks.values() if value is not None]
    return {
        "case_id": case.case_id,
        "checks": checks,
        "passed": all(evaluated_checks),
        "workflow_tools": workflow_records,
        "knowledge_document_ids": source_document_ids,
        "answer": state.get("answer") if mode == "live-rag" else None,
    }


def _fact_matches(expectation: ToolFactExpectation, state: AgentState) -> bool:
    result = next(
        (item for item in state["tool_results"] if item.name == expectation.tool_name), None
    )
    return result is not None and result.content.get(expectation.field) == expectation.expected


def _safety_matches(case: WorkflowCase, observed_statuses: dict[str, str]) -> bool | None:
    if case.safety_expectation is None:
        return None
    if case.safety_expectation == "cross_customer_denied":
        return observed_statuses.get("get_invoice") == "denied"
    return False


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _mean_check(
    reports: list[dict[str, object]], check_name: str, *, ignore_missing: bool = False
) -> float:
    values = [report["checks"][check_name] for report in reports]  # type: ignore[index]
    if ignore_missing:
        values = [value for value in values if value is not None]
    return _rate(sum(bool(value) for value in values), len(values))
