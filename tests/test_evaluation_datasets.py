from __future__ import annotations

from pathlib import Path

import pytest

from service_desk.evaluation.datasets import (
    load_retrieval_dataset,
    load_workflow_dataset,
    verify_all_held_out_manifests,
    verify_held_out_manifest,
)


def _datasets_root() -> Path:
    return Path(__file__).resolve().parents[1] / "evaluation" / "datasets"


def test_frozen_evaluation_dataset_sizes_and_metadata() -> None:
    root = _datasets_root()
    development_retrieval = load_retrieval_dataset(root / "development" / "retrieval-v1.json")
    held_out_retrieval = load_retrieval_dataset(root / "held_out" / "retrieval-v1.json")
    development_workflow = load_workflow_dataset(root / "development" / "workflow-v1.json")
    held_out_workflow = load_workflow_dataset(root / "held_out" / "workflow-v1.json")
    held_out_workflow_v2 = load_workflow_dataset(root / "held_out" / "workflow-v2.json")

    assert len(development_retrieval.cases) == 3
    assert len(held_out_retrieval.cases) == 6
    assert len(development_workflow.cases) == 3
    assert len(held_out_workflow.cases) == 6
    assert len(held_out_workflow_v2.cases) == 6
    assert {dataset.corpus_version for dataset in (development_retrieval, held_out_retrieval)} == {
        "kb-v1"
    }
    assert {dataset.chunking_version for dataset in (development_workflow, held_out_workflow)} == {
        "v1"
    }
    assert held_out_workflow_v2.dataset_id == "workflow-held-out-v2"
    assert held_out_workflow_v2.dataset_version == "v2"


def test_held_out_manifest_matches_exact_frozen_dataset_bytes() -> None:
    manifest = verify_held_out_manifest(_datasets_root() / "held_out")

    assert manifest.files == {
        "retrieval-v1.json": "b2224f88be1f7a0a4bf222f23e01e85b0aa7892f727e07d2897420a9d338311d",
        "workflow-v1.json": "54f9591478cdb6e37e76a9287ab72030be59362879d58288308b419422656469",
    }


def test_held_out_manifest_rejects_changed_data(tmp_path: Path) -> None:
    source = _datasets_root() / "held_out"
    for source_file in source.iterdir():
        (tmp_path / source_file.name).write_bytes(source_file.read_bytes())
    retrieval_path = tmp_path / "retrieval-v1.json"
    retrieval_path.write_text(retrieval_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="fingerprint mismatch"):
        verify_held_out_manifest(tmp_path)


def test_v2_manifest_freezes_only_the_new_workflow_dataset() -> None:
    manifests = verify_all_held_out_manifests(_datasets_root() / "held_out")

    assert manifests["manifest-v2.json"].files == {
        "workflow-v2.json": "5e40087d2786628485d29e9eb976343bf934d9aca94685bf9d9f5e7dd7fb3e9e"
    }
