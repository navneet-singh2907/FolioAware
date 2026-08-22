import json

import pytest

from folioaware.cli.main import build_parser, main


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
