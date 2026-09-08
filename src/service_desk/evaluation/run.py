"""Explicit CLI for reproducible V2 retrieval and grounded-workflow evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from service_desk.ai.openai_gateway import OpenAIModelGateway
from service_desk.config import Settings
from service_desk.data.repository import BusinessRepository
from service_desk.evaluation.datasets import (
    file_fingerprint,
    load_retrieval_dataset,
    load_workflow_dataset,
    verify_held_out_manifest,
)
from service_desk.evaluation.retrieval import evaluate_retrieval
from service_desk.evaluation.workflow import evaluate_workflows, run_offline_workflow_evaluation
from service_desk.graph.orchestrator import ServiceDeskGraph
from service_desk.knowledge.embeddings import OpenAIEmbeddingClient
from service_desk.knowledge.retrieval import DatabaseKnowledgeRetriever
from service_desk.tools.business import BusinessTools


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate V2 retrieval and grounded workflows.")
    parser.add_argument(
        "mode",
        choices=("validate", "workflow-offline", "retrieval-live", "workflow-live"),
    )
    parser.add_argument("--split", choices=("development", "held_out"), default="development")
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optionally run 1–3 live workflow cases; omit to run the complete selected split.",
    )
    parser.add_argument(
        "--start-at",
        type=int,
        default=1,
        help="1-based workflow case position for a live run; use a new output path when resuming.",
    )
    parser.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    arguments = parser.parse_args()

    root = Path(__file__).resolve().parents[3]
    datasets_root = root / "evaluation" / "datasets"
    if arguments.mode == "validate":
        report = _validation_report(datasets_root)
    elif arguments.mode == "workflow-offline":
        workflow_path = datasets_root / arguments.split / "workflow-v1.json"
        _verify_held_out_if_needed(datasets_root, arguments.split)
        report = run_offline_workflow_evaluation(
            load_workflow_dataset(workflow_path),
            dataset_path_fingerprint=file_fingerprint(workflow_path),
        )
    elif arguments.mode == "retrieval-live":
        _require_live_confirmation(arguments.confirm_live)
        retrieval_path = datasets_root / arguments.split / "retrieval-v1.json"
        _verify_held_out_if_needed(datasets_root, arguments.split)
        settings = _live_settings()
        dataset = load_retrieval_dataset(retrieval_path)
        _require_dataset_settings_match(dataset.corpus_version, dataset.chunking_version, dataset.embedding_model, settings)
        top_k = arguments.top_k if arguments.top_k is not None else settings.knowledge_default_top_k
        report = evaluate_retrieval(
            dataset,
            dataset_path_fingerprint=file_fingerprint(retrieval_path),
            retriever=_live_retriever(settings),
            top_k=top_k,
        )
        report["api_usage"] = "OpenAI embeddings were called once per retrieval case."
    else:
        _require_live_confirmation(arguments.confirm_live)
        workflow_path = datasets_root / arguments.split / "workflow-v1.json"
        _verify_held_out_if_needed(datasets_root, arguments.split)
        settings = _live_settings()
        dataset = load_workflow_dataset(workflow_path)
        _validate_workflow_live_selection(arguments.limit, arguments.start_at, len(dataset.cases))
        _require_dataset_settings_match(dataset.corpus_version, dataset.chunking_version, dataset.embedding_model, settings)
        graph = ServiceDeskGraph(
            BusinessTools(BusinessRepository.from_default_seed()),
            OpenAIModelGateway(settings.openai_api_key.get_secret_value(), settings.openai_model),  # type: ignore[union-attr]
            _live_retriever(settings),
        )
        report = evaluate_workflows(
            dataset,
            dataset_path_fingerprint=file_fingerprint(workflow_path),
            invoke_case=lambda case: graph.invoke(
                case.customer_id, case.message, request_id=f"live-evaluation-{case.case_id}"
            ),
            mode="live-rag",
            limit=arguments.limit,
            start_at=arguments.start_at - 1,
        )
        report["api_usage"] = (
            "OpenAI Responses and embeddings calls were made; answers require human review."
        )

    _emit(report, arguments.output)


def _validation_report(datasets_root: Path) -> dict[str, object]:
    manifest = verify_held_out_manifest(datasets_root / "held_out")
    files = {
        split: {
            filename: file_fingerprint(datasets_root / split / filename)
            for filename in ("retrieval-v1.json", "workflow-v1.json")
        }
        for split in ("development", "held_out")
    }
    return {
        "evaluation_type": "dataset_validation",
        "held_out_manifest_version": manifest.manifest_version,
        "corpus_version": manifest.corpus_version,
        "chunking_version": manifest.chunking_version,
        "embedding_model": manifest.embedding_model,
        "dataset_fingerprints": files,
    }


def _verify_held_out_if_needed(datasets_root: Path, split: str) -> None:
    if split == "held_out":
        verify_held_out_manifest(datasets_root / "held_out")


def _live_settings() -> Settings:
    settings = Settings()
    if settings.openai_api_key is None or settings.database_url is None:
        raise SystemExit("OPENAI_API_KEY and DATABASE_URL are required for live evaluation")
    return settings


def _live_retriever(settings: Settings) -> DatabaseKnowledgeRetriever:
    return DatabaseKnowledgeRetriever(
        database_url=settings.database_url.get_secret_value(),  # type: ignore[union-attr]
        embedding_client=OpenAIEmbeddingClient(settings.openai_api_key.get_secret_value()),  # type: ignore[union-attr]
        embedding_model=settings.openai_embedding_model,
        embedding_dimensions=settings.openai_embedding_dimensions,
        corpus_version=settings.knowledge_corpus_version,
        default_top_k=settings.knowledge_default_top_k,
    )


def _require_dataset_settings_match(
    corpus_version: str, chunking_version: str, embedding_model: str, settings: Settings
) -> None:
    if corpus_version != settings.knowledge_corpus_version:
        raise SystemExit("evaluation dataset corpus_version does not match configured knowledge corpus")
    if chunking_version != "v1":
        raise SystemExit("evaluation dataset chunking_version is not supported by this runner")
    if embedding_model != settings.openai_embedding_model:
        raise SystemExit("evaluation dataset embedding_model does not match configured embedding model")


def _require_live_confirmation(confirmed: bool) -> None:
    if not confirmed:
        raise SystemExit("this mode uses OpenAI APIs; rerun with --confirm-live to proceed")
    print("Live evaluation will use OpenAI APIs and may incur charges.", file=sys.stderr)


def _validate_workflow_live_selection(
    limit: int | None, start_at: int, available_case_count: int
) -> None:
    if limit is not None and not 1 <= limit <= 3:
        raise SystemExit("workflow-live --limit must be between 1 and 3 when supplied")
    if not 1 <= start_at <= available_case_count:
        raise SystemExit(f"workflow-live --start-at must be between 1 and {available_case_count}")


def _emit(report: dict[str, object], output: Path | None) -> None:
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
