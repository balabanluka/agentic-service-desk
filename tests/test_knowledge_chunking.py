from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from service_desk.knowledge import FROZEN_SOURCE_COMMIT, KnowledgeBaseChunker, KnowledgeDocumentError


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIRECTORY = REPOSITORY_ROOT / "knowledge"


def test_frozen_corpus_has_stable_chunk_metadata_and_expected_count() -> None:
    chunker = KnowledgeBaseChunker()

    first_run = chunker.chunk_directory(KNOWLEDGE_DIRECTORY, repository_root=REPOSITORY_ROOT)
    second_run = chunker.chunk_directory(KNOWLEDGE_DIRECTORY, repository_root=REPOSITORY_ROOT)

    assert first_run == second_run
    assert len(first_run) == 20
    assert [chunk.chunk_id for chunk in first_run] == [
        "KB-BIL-001--chunk-v1--001",
        "KB-BIL-001--chunk-v1--002",
        "KB-BIL-002--chunk-v1--001",
        "KB-BIL-003--chunk-v1--001",
        "KB-BIL-004--chunk-v1--001",
        "KB-BIL-005--chunk-v1--001",
        "KB-BIL-005--chunk-v1--002",
        "KB-BIL-006--chunk-v1--001",
        "KB-SUP-001--chunk-v1--001",
        "KB-SUP-002--chunk-v1--001",
        "KB-SUP-003--chunk-v1--001",
        "KB-SUP-004--chunk-v1--001",
        "KB-SUP-005--chunk-v1--001",
        "KB-SUP-006--chunk-v1--001",
        "KB-TEC-001--chunk-v1--001",
        "KB-TEC-002--chunk-v1--001",
        "KB-TEC-003--chunk-v1--001",
        "KB-TEC-004--chunk-v1--001",
        "KB-TEC-005--chunk-v1--001",
        "KB-TEC-006--chunk-v1--001",
    ]
    assert all(chunk.source_path.startswith("knowledge/") for chunk in first_run)
    assert all("\\" not in chunk.source_path for chunk in first_run)
    assert all(chunk.source_commit == FROZEN_SOURCE_COMMIT for chunk in first_run)
    assert all(chunk.word_count == len(chunk.content.split()) for chunk in first_run)
    assert all(chunk.content_sha256 == sha256(chunk.content.encode("utf-8")).hexdigest() for chunk in first_run)
    assert all(
        all(f"{field}:" not in chunk.content for field in ("document_id", "title", "domain", "product"))
        for chunk in first_run
    )
    assert max(chunk.word_count for chunk in first_run) <= 600


def test_front_matter_is_required_and_not_chunk_content(tmp_path: Path) -> None:
    source = tmp_path / "knowledge" / "support" / "example.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "---\n"
        "document_id: KB-SUP-999\n"
        "title: Example\n"
        "domain: support\n"
        "product: Harborlight Workspace\n"
        "---\n\n"
        "# Example\n\n"
        "Introductory text belongs to the first section.\n\n"
        "## First section\n\n"
        "Useful content.\n",
        encoding="utf-8",
    )
    chunk = KnowledgeBaseChunker().chunk_directory(source.parents[1], repository_root=tmp_path)[0]

    assert chunk.document_title == "Example"
    assert chunk.heading_path == ("Example", "First section")
    assert "document_id:" not in chunk.content
    assert "Introductory text" in chunk.content

    source.write_text("# Missing front matter\n", encoding="utf-8")
    with pytest.raises(KnowledgeDocumentError, match="front matter"):
        KnowledgeBaseChunker().chunk_directory(source.parents[1], repository_root=tmp_path)


def test_headings_inside_fenced_code_do_not_change_heading_paths(tmp_path: Path) -> None:
    source = tmp_path / "knowledge" / "technical" / "fenced.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "---\n"
        "document_id: KB-TEC-999\n"
        "title: Fenced example\n"
        "domain: technical\n"
        "product: Harborlight Workspace\n"
        "---\n\n"
        "# Fenced example\n\n"
        "## Real section\n\n"
        "```markdown\n"
        "## Not a real heading\n"
        "```\n\n"
        "Paragraph after the code block.\n",
        encoding="utf-8",
    )

    chunk = KnowledgeBaseChunker().chunk_directory(source.parents[1], repository_root=tmp_path)[0]

    assert chunk.heading_path == ("Fenced example", "Real section")
    assert chunk.included_heading_paths == (("Fenced example", "Real section"),)
    assert "## Not a real heading" in chunk.content


def test_oversized_h2_splits_at_paragraph_boundaries_without_cross_document_content(
    tmp_path: Path,
) -> None:
    source = tmp_path / "knowledge" / "billing" / "large.md"
    source.parent.mkdir(parents=True)
    paragraph = " ".join(f"word{index}" for index in range(210))
    source.write_text(
        "---\n"
        "document_id: KB-BIL-999\n"
        "title: Large example\n"
        "domain: billing\n"
        "product: Harborlight Workspace\n"
        "---\n\n"
        "# Large example\n\n"
        "## Large section\n\n"
        f"{paragraph}\n\n{paragraph}\n\n{paragraph}\n",
        encoding="utf-8",
    )

    chunks = KnowledgeBaseChunker().chunk_directory(source.parents[1], repository_root=tmp_path)

    assert len(chunks) == 2
    assert all(chunk.word_count <= 600 for chunk in chunks)
    assert all("## Large section" in chunk.content for chunk in chunks)
    assert all(chunk.source_path == "knowledge/billing/large.md" for chunk in chunks)
