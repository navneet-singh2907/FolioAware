"""FolioAware command-line interface."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from folioaware.adapters.local import (
    DeterministicEmbeddingProvider,
    InMemoryKnowledgeRepository,
    SystemClock,
    UUID4Provider,
)
from folioaware.application.sync_knowledge import SyncKnowledge
from folioaware.ingestion import load_approved_sources


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser without reading process-global state."""
    parser = argparse.ArgumentParser(prog="folioaware")
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    commands = parser.add_subparsers(dest="command")
    sync = commands.add_parser(
        "sync",
        help="validate and synchronize approved content into a local index",
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


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parsed = build_parser().parse_args(arguments)
    if parsed.command == "sync":
        repository = InMemoryKnowledgeRepository()
        result = SyncKnowledge(
            embeddings=DeterministicEmbeddingProvider(),
            repository=repository,
            clock=SystemClock(),
            identifiers=UUID4Provider(),
        ).execute(
            sources=load_approved_sources(parsed.content_root),
            git_commit=parsed.git_commit,
        )
        print(json.dumps(result.model_dump(mode="json", by_alias=True), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
