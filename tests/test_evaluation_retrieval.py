from __future__ import annotations

from service_desk.evaluation.models import RetrievalCase, RetrievalDataset
from service_desk.evaluation.retrieval import evaluate_retrieval
from service_desk.knowledge.retrieval import KnowledgeSearchResult


def _result(*, rank: int, document_id: str, chunk_id: str) -> KnowledgeSearchResult:
    return KnowledgeSearchResult(
        rank=rank,
        chunk_id=chunk_id,
        chunking_version="v1",
        corpus_version="kb-v1",
        document_id=document_id,
        document_title=document_id,
        domain="technical",
        product="Harborlight Cloud",
        heading_path=(document_id,),
        included_heading_paths=((document_id,),),
        chunk_index=rank,
        source_path=f"knowledge/{document_id}.md",
        content="Synthetic result.",
        word_count=2,
        content_sha256="a" * 64,
        source_commit="b" * 40,
        cosine_distance=float(rank) / 10,
        cosine_similarity=1 - float(rank) / 10,
    )


class FakeRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None, int | None]] = []

    def search(self, query: str, *, domain: str | None = None, top_k: int | None = None):
        self.calls.append((query, domain, top_k))
        if query == "first":
            return (_result(rank=1, document_id="DOC-1", chunk_id="chunk-1"),)
        return (
            _result(rank=1, document_id="OTHER", chunk_id="other"),
            _result(rank=2, document_id="DOC-2", chunk_id="chunk-2"),
        )


def test_retrieval_metrics_include_actual_rankings_failures_and_per_domain() -> None:
    dataset = RetrievalDataset(
        dataset_id="test-retrieval-v1",
        dataset_version="v1",
        corpus_version="kb-v1",
        chunking_version="v1",
        embedding_model="text-embedding-3-small",
        cases=(
            RetrievalCase(
                case_id="case-one", query="first", expected_domain="technical", expected_document_ids=("DOC-1",)
            ),
            RetrievalCase(
                case_id="case-two", query="second", expected_domain="billing", acceptable_chunk_ids=("chunk-2",)
            ),
        ),
    )
    retriever = FakeRetriever()

    report = evaluate_retrieval(
        dataset,
        dataset_path_fingerprint="fingerprint",
        retriever=retriever,
        top_k=4,
    )

    assert report["hit_at_1"] == 0.5
    assert report["hit_at_k"] == 1.0
    assert report["mean_reciprocal_rank"] == 0.75
    assert report["failures"] == []
    assert report["per_domain"]["technical"]["hit_at_1"] == 1.0
    assert report["cases"][1]["actual_ranking"][1]["chunk_id"] == "chunk-2"
    assert retriever.calls == [("first", "technical", 4), ("second", "billing", 4)]


def test_retrieval_report_keeps_missed_case_ranking_as_failure() -> None:
    dataset = RetrievalDataset(
        dataset_id="test-retrieval-failure-v1",
        dataset_version="v1",
        corpus_version="kb-v1",
        chunking_version="v1",
        embedding_model="text-embedding-3-small",
        cases=(
            RetrievalCase(
                case_id="case-miss", query="second", expected_domain="technical", expected_document_ids=("MISSING",)
            ),
        ),
    )

    report = evaluate_retrieval(
        dataset,
        dataset_path_fingerprint="fingerprint",
        retriever=FakeRetriever(),
        top_k=4,
    )

    assert report["hit_at_1"] == 0.0
    assert report["failures"][0]["case_id"] == "case-miss"
    assert report["failures"][0]["actual_ranking"][0]["document_id"] == "OTHER"
