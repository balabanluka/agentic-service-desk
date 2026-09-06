"""Metric computation for the existing V2 retriever without ranking changes."""

from __future__ import annotations

from collections import defaultdict

from service_desk.evaluation.models import RetrievalCase, RetrievalDataset
from service_desk.knowledge.retrieval import KnowledgeSearchProvider


def evaluate_retrieval(
    dataset: RetrievalDataset,
    *,
    dataset_path_fingerprint: str,
    retriever: KnowledgeSearchProvider,
    top_k: int,
) -> dict[str, object]:
    """Evaluate retrieval outputs exactly as returned by the supplied retriever."""

    if not 1 <= top_k <= 10:
        raise ValueError("top_k must be between 1 and 10")

    case_reports = [_evaluate_case(case, retriever, top_k) for case in dataset.cases]
    failures = [report for report in case_reports if not report["hit_at_k"]]
    return {
        "evaluation_type": "retrieval",
        "dataset_id": dataset.dataset_id,
        "dataset_version": dataset.dataset_version,
        "dataset_fingerprint": dataset_path_fingerprint,
        "corpus_version": dataset.corpus_version,
        "chunking_version": dataset.chunking_version,
        "embedding_model": dataset.embedding_model,
        "top_k": top_k,
        "case_count": len(case_reports),
        "hit_at_1": _mean(report["hit_at_1"] for report in case_reports),
        "hit_at_k": _mean(report["hit_at_k"] for report in case_reports),
        "mean_reciprocal_rank": _mean(report["reciprocal_rank"] for report in case_reports),
        "per_domain": _per_domain_metrics(case_reports),
        "cases": case_reports,
        "failures": failures,
    }


def _evaluate_case(
    case: RetrievalCase, retriever: KnowledgeSearchProvider, top_k: int
) -> dict[str, object]:
    results = retriever.search(case.query, domain=case.expected_domain, top_k=top_k)
    match_rank = next(
        (
            result.rank
            for result in results
            if result.document_id in case.expected_document_ids
            or result.chunk_id in case.acceptable_chunk_ids
        ),
        None,
    )
    ranking = [
        {
            "rank": result.rank,
            "document_id": result.document_id,
            "chunk_id": result.chunk_id,
            "cosine_distance": result.cosine_distance,
            "cosine_similarity": result.cosine_similarity,
        }
        for result in results
    ]
    return {
        "case_id": case.case_id,
        "expected_domain": case.expected_domain,
        "expected_document_ids": list(case.expected_document_ids),
        "acceptable_chunk_ids": list(case.acceptable_chunk_ids),
        "match_rank": match_rank,
        "hit_at_1": match_rank == 1,
        "hit_at_k": match_rank is not None and match_rank <= top_k,
        "reciprocal_rank": 0.0 if match_rank is None else 1.0 / match_rank,
        "actual_ranking": ranking,
    }


def _per_domain_metrics(case_reports: list[dict[str, object]]) -> dict[str, dict[str, float]]:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for report in case_reports:
        groups[str(report["expected_domain"] or "unfiltered")].append(report)
    return {
        domain: {
            "case_count": len(reports),
            "hit_at_1": _mean(report["hit_at_1"] for report in reports),
            "hit_at_k": _mean(report["hit_at_k"] for report in reports),
            "mean_reciprocal_rank": _mean(report["reciprocal_rank"] for report in reports),
        }
        for domain, reports in sorted(groups.items())
    }


def _mean(values: object) -> float:
    materialized = [float(value) for value in values]  # type: ignore[arg-type]
    return sum(materialized) / len(materialized) if materialized else 0.0
