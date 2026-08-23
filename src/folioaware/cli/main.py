"""FolioAware command-line interface."""

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import ValidationError

from folioaware.cli.dependencies import SyncCommandContainer, build_sync_container
from folioaware.config import SyncSettings
from folioaware.domain.exceptions import (
    FolioAwareError,
    KnowledgeUnavailableError,
    ModelUnavailableError,
    SyncConflictError,
    SyncValidationError,
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
    return parser


def main(
    arguments: Sequence[str] | None = None,
    *,
    sync_container_factory: Callable[[SyncSettings], SyncCommandContainer] = (
        build_sync_container
    ),
) -> int:
    """Run the CLI and return a process exit code."""
    parsed = build_parser().parse_args(arguments)
    if parsed.command == "sync":
        try:
            settings = SyncSettings(
                **({"backend": parsed.backend} if parsed.backend is not None else {})
            )
            container = sync_container_factory(settings)
            result = container.sync_knowledge.execute(
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


if __name__ == "__main__":
    raise SystemExit(main())
