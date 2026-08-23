import json
from typing import cast
from unittest.mock import MagicMock

import pytest

from folioaware.application.sync_knowledge import SyncKnowledge
from folioaware.cli.dependencies import SyncCommandContainer, build_sync_container
from folioaware.cli.main import _cli_error_code, build_parser, main
from folioaware.config import SyncSettings
from folioaware.domain.exceptions import (
    KnowledgeUnavailableError,
    ModelUnavailableError,
    SyncConflictError,
    SyncValidationError,
)


def test_cli_without_command_succeeds() -> None:
    assert main([]) == 0


def test_cli_reports_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(["--version"])

    assert error.value.code == 0
    assert capsys.readouterr().out.strip() == "folioaware 0.1.0"


def test_cli_syncs_synthetic_approved_content(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        [
            "sync",
            "--content-root",
            "examples/synthetic-portfolio",
            "--git-commit",
            "abcdef1",
        ]
    )

    body = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert body["status"] == "succeeded"
    assert body["sourcesSeen"] == 3
    assert body["chunksAdded"] == 3


def test_cli_selects_google_sync_without_constructing_api_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("FOLIOAWARE_GOOGLE_CLOUD_PROJECT", "synthetic-project")
    captured: list[SyncSettings] = []

    def factory(settings: SyncSettings) -> SyncCommandContainer:
        captured.append(settings)
        return build_sync_container(SyncSettings())

    exit_code = main(
        [
            "sync",
            "--backend",
            "google",
            "--content-root",
            "examples/synthetic-portfolio",
            "--git-commit",
            "abcdef1",
        ],
        sync_container_factory=factory,
    )

    assert exit_code == 0
    assert captured[0].backend == "google"
    assert captured[0].google_cloud_project == "synthetic-project"
    assert json.loads(capsys.readouterr().out)["status"] == "succeeded"


def test_cli_reports_sanitized_configuration_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("FOLIOAWARE_GOOGLE_CLOUD_PROJECT", raising=False)

    exit_code = main(["sync", "--backend", "google"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "errorCode": "INVALID_CONFIGURATION",
        "status": "failed",
    }


def test_cli_does_not_print_vendor_failure_details(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sync = MagicMock(spec=SyncKnowledge)
    sync.execute.side_effect = ModelUnavailableError("sensitive vendor detail")

    def factory(settings: SyncSettings) -> SyncCommandContainer:
        return SyncCommandContainer(sync_knowledge=cast(SyncKnowledge, sync))

    exit_code = main(
        [
            "sync",
            "--content-root",
            "examples/synthetic-portfolio",
            "--git-commit",
            "abcdef1",
        ],
        sync_container_factory=factory,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "sensitive vendor detail" not in captured.err
    assert json.loads(captured.err)["errorCode"] == "EMBEDDING_UNAVAILABLE"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (SyncConflictError(), "SYNC_CONFLICT"),
        (KnowledgeUnavailableError(), "KNOWLEDGE_UNAVAILABLE"),
        (SyncValidationError(), "SYNC_VALIDATION_FAILED"),
        (OSError(), "SYNC_INPUT_UNAVAILABLE"),
    ],
)
def test_cli_uses_stable_sanitized_error_codes(error: Exception, expected: str) -> None:
    assert _cli_error_code(error) == expected
