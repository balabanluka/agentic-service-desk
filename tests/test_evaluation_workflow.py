from __future__ import annotations

from pathlib import Path

from service_desk.evaluation.datasets import file_fingerprint, load_workflow_dataset
from service_desk.evaluation.workflow import run_offline_workflow_evaluation


def test_offline_workflow_evaluation_exercises_routes_sources_tools_and_safety() -> None:
    path = Path(__file__).resolve().parents[1] / "evaluation" / "datasets" / "held_out" / "workflow-v1.json"

    report = run_offline_workflow_evaluation(
        load_workflow_dataset(path), dataset_path_fingerprint=file_fingerprint(path)
    )

    assert report["case_count"] == 6
    assert report["passed_case_rate"] == 1.0
    assert report["route_accuracy"] == 1.0
    assert report["knowledge_source_coverage"] == 1.0
    assert report["safety_rate"] == 1.0
    cross_customer = next(case for case in report["cases"] if case["case_id"] == "hold-rag-cross-customer-invoice")
    assert cross_customer["checks"]["customer_facts_grounded"] is True
    forbidden = next(case for case in report["cases"] if case["case_id"] == "hold-rag-forbidden-tool")
    assert forbidden["checks"]["safety_expectation_met"] is True
