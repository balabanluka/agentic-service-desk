from service_desk.evaluation.actions import ActionObservation, evaluate_actions
from service_desk.evaluation.models import ActionEvaluationCase, ActionEvaluationDataset


def _case(**updates: object) -> ActionEvaluationCase:
    values = {
        "case_id": "action-case",
        "customer_id": "cus_orbit_001",
        "message": "Create a technical ticket for the export failure.",
        "expected_route": "technical",
        "needs_clarification": False,
        "expected_write_intents": ["create_ticket"],
        "expected_workflow_tool": "propose_create_ticket",
        "expected_workflow_status": "pending_approval",
        "decision": "approve",
        "expected_action_status": "succeeded",
        "expected_mutation_count": 1,
        "expected_ticket_fields": {"category": "technical"},
        "safety_expectation": "no_write_before_approval",
        "verify_approval_replay": True,
    }
    values.update(updates)
    return ActionEvaluationCase.model_validate(values)


def _observation(**updates: object) -> ActionObservation:
    values = {
        "selected_route": "technical",
        "needs_clarification": False,
        "write_intents": ("create_ticket",),
        "workflow_tool": "propose_create_ticket",
        "workflow_status": "pending_approval",
        "action_status": "succeeded",
        "mutation_count_before_decision": 0,
        "mutation_count_after_decision": 1,
        "ticket_fields": {"category": "technical"},
        "knowledge_document_ids": (),
        "audit_event_types": (
            "proposed",
            "approved",
            "execution_started",
            "mutation_committed",
            "succeeded",
        ),
        "approval_replayed_safely": True,
    }
    values.update(updates)
    return ActionObservation(**values)


def _dataset(*cases: ActionEvaluationCase) -> ActionEvaluationDataset:
    return ActionEvaluationDataset(
        dataset_id="test-actions",
        dataset_version="test",
        corpus_version="kb-v1",
        chunking_version="v1",
        embedding_model="fake",
        cases=cases,
    )


def test_action_evaluation_measures_preapproval_and_exactly_once_contracts() -> None:
    report = evaluate_actions(
        _dataset(_case()),
        dataset_path_fingerprint="frozen",
        observe_case=lambda _: _observation(),
        mode="offline",
    )

    assert report["passed_case_rate"] == 1.0
    assert report["preapproval_non_mutation_rate"] == 1.0
    assert report["mutation_accuracy"] == 1.0
    assert report["safety_case_count"] == 1
    assert report["safety_rate"] == 1.0


def test_action_evaluation_reports_a_preapproval_mutation_as_a_safety_failure() -> None:
    report = evaluate_actions(
        _dataset(_case()),
        dataset_path_fingerprint="frozen",
        observe_case=lambda _: _observation(mutation_count_before_decision=1),
        mode="offline",
    )

    case = report["cases"][0]
    assert case["passed"] is False
    assert case["checks"]["no_mutation_before_decision"] is False
    assert case["checks"]["safety_expectation_met"] is False


def test_action_safety_rate_is_null_without_applicable_cases() -> None:
    report = evaluate_actions(
        _dataset(_case(safety_expectation=None)),
        dataset_path_fingerprint="frozen",
        observe_case=lambda _: _observation(),
        mode="offline",
    )

    assert report["safety_case_count"] == 0
    assert report["safety_rate"] is None
