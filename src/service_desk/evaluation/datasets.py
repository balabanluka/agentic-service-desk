"""Dataset loading and frozen held-out fingerprint verification."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from service_desk.evaluation.models import HeldOutManifest, RetrievalDataset, WorkflowDataset


def file_fingerprint(path: Path) -> str:
    """Return a line-ending-independent SHA-256 fingerprint of frozen JSON text."""

    content = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return sha256(content.encode("utf-8")).hexdigest()


def load_retrieval_dataset(path: Path) -> RetrievalDataset:
    return RetrievalDataset.model_validate_json(path.read_text(encoding="utf-8"))


def load_workflow_dataset(path: Path) -> WorkflowDataset:
    return WorkflowDataset.model_validate_json(path.read_text(encoding="utf-8"))


def verify_held_out_manifest(directory: Path) -> HeldOutManifest:
    """Reject changed held-out data before an evaluation can report its metrics."""

    manifest = HeldOutManifest.model_validate_json(
        (directory / "manifest-v1.json").read_text(encoding="utf-8")
    )
    for filename, expected_fingerprint in manifest.files.items():
        actual_fingerprint = file_fingerprint(directory / filename)
        if actual_fingerprint != expected_fingerprint:
            raise ValueError(
                f"held-out dataset fingerprint mismatch for {filename}: "
                f"expected {expected_fingerprint}, got {actual_fingerprint}"
            )
    return manifest
