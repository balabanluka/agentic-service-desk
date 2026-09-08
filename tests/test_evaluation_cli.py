from __future__ import annotations

import sys
from pathlib import Path

import pytest

from service_desk.evaluation import run


def test_validation_cli_runs_without_settings_or_openai(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["evaluation", "validate"])

    run.main()

    output = capsys.readouterr().out
    assert '"evaluation_type": "dataset_validation"' in output
    assert '"held_out_manifest_version": "v1"' in output
    assert '"manifest-v2.json"' in output


def test_live_cli_requires_explicit_confirmation_before_loading_settings(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["evaluation", "retrieval-live"])

    with pytest.raises(SystemExit, match="confirm-live"):
        run.main()


def test_workflow_live_selection_allows_full_or_bounded_resume_runs() -> None:
    run._validate_workflow_live_selection(None, 1, 6)
    run._validate_workflow_live_selection(1, 4, 6)
    run._validate_workflow_live_selection(3, 4, 6)

    with pytest.raises(SystemExit, match="when supplied"):
        run._validate_workflow_live_selection(4, 1, 6)
    with pytest.raises(SystemExit, match="start-at"):
        run._validate_workflow_live_selection(None, 7, 6)


def test_workflow_v2_path_is_available_only_for_the_held_out_split() -> None:
    datasets_root = Path("evaluation/datasets")

    assert run._workflow_dataset_path(datasets_root, "held_out", "v2") == (
        datasets_root / "held_out" / "workflow-v2.json"
    )
    with pytest.raises(SystemExit, match="held-out"):
        run._workflow_dataset_path(datasets_root, "development", "v2")
