from __future__ import annotations

import sys

import pytest

from service_desk.evaluation import run


def test_validation_cli_runs_without_settings_or_openai(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["evaluation", "validate"])

    run.main()

    output = capsys.readouterr().out
    assert '"evaluation_type": "dataset_validation"' in output
    assert '"held_out_manifest_version": "v1"' in output


def test_live_cli_requires_explicit_confirmation_before_loading_settings(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["evaluation", "retrieval-live"])

    with pytest.raises(SystemExit, match="confirm-live"):
        run.main()
