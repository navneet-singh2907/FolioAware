import json
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest

from folioaware.application.sync_knowledge import SyncKnowledge
from folioaware.cli.dependencies import SyncCommandContainer, build_sync_container
from folioaware.cli.main import (
    _cli_error_code,
    _evaluation_cli_error_code,
    build_parser,
    main,
)
from folioaware.config import SyncSettings
from folioaware.domain.exceptions import (
    KnowledgeUnavailableError,
    ModelUnavailableError,
    SyncConflictError,
    SyncValidationError,
)
from folioaware.evaluation import EvaluationValidationError


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
    sync.execute.side_effect = ModelUnavailableError(
        "sensitive vendor detail",
        provider_error_type="APIError",
        provider_status="UNAUTHENTICATED",
    )

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
    assert json.loads(captured.err) == {
        "diagnostic": {
            "providerErrorType": "APIError",
            "providerStatus": "UNAUTHENTICATED",
        },
        "errorCode": "EMBEDDING_UNAVAILABLE",
        "status": "failed",
    }


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


def test_cli_evaluation_is_stable_and_passes_safe_threshold(
    capsys: pytest.CaptureFixture[str],
) -> None:
    arguments = ["evaluate", "--git-commit", "4770cb3"]

    first_exit = main(arguments)
    first = capsys.readouterr()
    second_exit = main(arguments)
    second = capsys.readouterr()

    report = json.loads(first.out)
    assert first_exit == second_exit == 0
    assert first.out == second.out
    assert first.err == second.err == ""
    assert report["passed"] is True
    assert report["suite"]["caseCount"] == 24
    assert report["configuration"]["generatorId"] == "local-extractive-v1"
    assert report["metrics"]["unsupportedAnswerRate"]["numerator"] == 0
    assert report["metrics"]["answerCoverage"]["numerator"] == 10
    assert report["gates"][-1] == {
        "name": "evaluation_isolation",
        "passed": True,
    }


def test_cli_writes_the_same_evaluation_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "nested" / "report.json"

    exit_code = main(["evaluate", "--output", str(output)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert output.read_text(encoding="utf-8") == captured.out


def test_cli_compares_against_an_accepted_baseline(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline = tmp_path / "baseline.json"
    assert (
        main(
            [
                "evaluate",
                "--git-commit",
                "4770cb3",
                "--output",
                str(baseline),
            ]
        )
        == 0
    )
    capsys.readouterr()

    exit_code = main(
        [
            "evaluate",
            "--git-commit",
            "4770cb3",
            "--baseline",
            str(baseline),
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["baselineComparison"]["passed"] is True
    assert report["baselineComparison"]["failureReasons"] == []

    regression_exit = main(
        [
            "evaluate",
            "--git-commit",
            "4770cb3",
            "--distance-threshold",
            "0.70",
            "--baseline",
            str(baseline),
        ]
    )
    regression = json.loads(capsys.readouterr().out)
    assert regression_exit == 1
    assert "configuration_changed" in regression["baselineComparison"]["failureReasons"]
    assert (
        "metric_regressed:aggregate:answer_coverage"
        in regression["baselineComparison"]["failureReasons"]
    )


def test_cli_evaluation_returns_two_for_invalid_input(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing.yaml"

    exit_code = main(["evaluate", "--suite", str(missing)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "errorCode": "INVALID_EVALUATION_INPUT",
        "status": "failed",
    }


def test_cli_evaluation_returns_two_for_invalid_baseline(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{}", encoding="utf-8")

    exit_code = main(["evaluate", "--baseline", str(baseline)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "errorCode": "INVALID_EVALUATION_INPUT",
        "status": "failed",
    }


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (EvaluationValidationError(), "INVALID_EVALUATION_INPUT"),
        (ModelUnavailableError(), "EMBEDDING_OR_GENERATION_UNAVAILABLE"),
        (KnowledgeUnavailableError(), "KNOWLEDGE_UNAVAILABLE"),
        (OSError(), "EVALUATION_INPUT_UNAVAILABLE"),
    ],
)
def test_evaluation_cli_uses_stable_error_codes(
    error: Exception, expected: str
) -> None:
    assert _evaluation_cli_error_code(error) == expected
