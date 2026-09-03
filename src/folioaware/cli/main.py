"""FolioAware command-line interface."""

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import ValidationError

from folioaware.cli.dependencies import (
    EvaluationCommandContainer,
    SyncCommandContainer,
    build_evaluation_container,
    build_sync_container,
)
from folioaware.config import SyncSettings
from folioaware.domain.exceptions import (
    FolioAwareError,
    KnowledgeUnavailableError,
    ModelUnavailableError,
    SyncConflictError,
    SyncValidationError,
)
from folioaware.domain.knowledge import ApprovedSource
from folioaware.evaluation import EvaluationValidationError, load_evaluation_suite
from folioaware.evaluation.report import (
    attach_baseline_comparison,
    compare_with_baseline,
    load_report,
    serialize_report,
)
from folioaware.ingestion import load_approved_sources


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser without reading process-global state."""
    parser = argparse.ArgumentParser(prog="folioaware")
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    commands = parser.add_subparsers(dest="command")
    sync = commands.add_parser(
        "sync",
        help="validate and synchronize explicitly approved portfolio content",
    )
    sync.add_argument(
        "--backend",
        choices=("local", "google"),
        default=None,
        help="override FOLIOAWARE_BACKEND for this synchronization",
    )
    sync.add_argument(
        "--content-root",
        type=Path,
        default=Path("examples/synthetic-portfolio"),
    )
    sync.add_argument(
        "--git-commit",
        default="0000000",
        help="7-64 lowercase hexadecimal characters identifying the content revision",
    )
    evaluate = commands.add_parser(
        "evaluate",
        help="run the deterministic offline RAG evaluation harness",
    )
    evaluate.add_argument(
        "--suite",
        type=Path,
        default=Path("evals/fixtures/synthetic-portfolio-v1.yaml"),
    )
    evaluate.add_argument(
        "--content-root",
        type=Path,
        default=Path("examples/synthetic-portfolio"),
    )
    evaluate.add_argument(
        "--git-commit",
        default="0000000",
        help="7-64 lowercase hexadecimal characters identifying the content revision",
    )
    evaluate.add_argument("--distance-threshold", type=float, default=0.72)
    evaluate.add_argument("--top-k", type=int, choices=range(1, 6), default=5)
    evaluate.add_argument(
        "--baseline",
        type=Path,
        help="compare against an accepted report and fail on any regression",
    )
    evaluate.add_argument(
        "--output",
        type=Path,
        help="optionally write the same stable JSON report printed to stdout",
    )
    return parser


def main(
    arguments: Sequence[str] | None = None,
    *,
    sync_container_factory: Callable[[SyncSettings], SyncCommandContainer] = (
        build_sync_container
    ),
    evaluation_container_factory: Callable[
        [tuple[ApprovedSource, ...], str, float, int], EvaluationCommandContainer
    ] = build_evaluation_container,
) -> int:
    """Run the CLI and return a process exit code."""
    parsed = build_parser().parse_args(arguments)
    if parsed.command == "sync":
        try:
            settings = SyncSettings(
                **({"backend": parsed.backend} if parsed.backend is not None else {})
            )
            sync_container = sync_container_factory(settings)
            result = sync_container.sync_knowledge.execute(
                sources=load_approved_sources(parsed.content_root),
                git_commit=parsed.git_commit,
            )
        except (FolioAwareError, ValidationError, OSError) as error:
            failure = {
                "status": "failed",
                "errorCode": _cli_error_code(error),
            }
            print(json.dumps(failure, sort_keys=True), file=sys.stderr)
            return 1
        print(json.dumps(result.model_dump(mode="json", by_alias=True), sort_keys=True))
    if parsed.command == "evaluate":
        try:
            sources = load_approved_sources(parsed.content_root)
            suite = load_evaluation_suite(parsed.suite, approved_sources=sources)
            evaluation_container = evaluation_container_factory(
                sources,
                parsed.git_commit,
                parsed.distance_threshold,
                parsed.top_k,
            )
            report = evaluation_container.runner.run(suite)
            if parsed.baseline is not None:
                comparison = compare_with_baseline(
                    report,
                    load_report(parsed.baseline),
                )
                report = attach_baseline_comparison(report, comparison)
            payload = serialize_report(report)
            if parsed.output is not None:
                parsed.output.parent.mkdir(parents=True, exist_ok=True)
                parsed.output.write_text(payload + "\n", encoding="utf-8", newline="\n")
        except (
            EvaluationValidationError,
            FolioAwareError,
            OSError,
            ValidationError,
            ValueError,
        ) as error:
            failure = {
                "status": "failed",
                "errorCode": _evaluation_cli_error_code(error),
            }
            print(json.dumps(failure, sort_keys=True), file=sys.stderr)
            return 2
        print(payload)
        return 0 if report.passed else 1
    return 0


def _cli_error_code(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "INVALID_CONFIGURATION"
    if isinstance(error, SyncConflictError):
        return "SYNC_CONFLICT"
    if isinstance(error, ModelUnavailableError):
        return "EMBEDDING_UNAVAILABLE"
    if isinstance(error, KnowledgeUnavailableError):
        return "KNOWLEDGE_UNAVAILABLE"
    if isinstance(error, SyncValidationError):
        return "SYNC_VALIDATION_FAILED"
    return "SYNC_INPUT_UNAVAILABLE"


def _evaluation_cli_error_code(error: Exception) -> str:
    if isinstance(error, (EvaluationValidationError, ValidationError, ValueError)):
        return "INVALID_EVALUATION_INPUT"
    if isinstance(error, ModelUnavailableError):
        return "EMBEDDING_OR_GENERATION_UNAVAILABLE"
    if isinstance(error, KnowledgeUnavailableError):
        return "KNOWLEDGE_UNAVAILABLE"
    return "EVALUATION_INPUT_UNAVAILABLE"


if __name__ == "__main__":
    raise SystemExit(main())
