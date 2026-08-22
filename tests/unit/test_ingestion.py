from pathlib import Path

import pytest

from folioaware.domain.exceptions import SyncValidationError
from folioaware.ingestion import load_approved_sources


def test_loads_only_manifest_approved_synthetic_sources() -> None:
    sources = load_approved_sources(Path("examples/synthetic-portfolio"))

    assert [source.source_id for source in sources] == [
        "project-atlas",
        "project-lantern",
        "project-meadow",
    ]


def test_rejects_source_path_that_escapes_content_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside.yaml"
    outside.write_text("not: relevant", encoding="utf-8")
    root = tmp_path / "portfolio"
    root.mkdir()
    (root / "folioaware.yaml").write_text(
        "schemaVersion: 1\nsources:\n  - path: ../outside.yaml\n",
        encoding="utf-8",
    )

    with pytest.raises(SyncValidationError, match="escapes the content root"):
        load_approved_sources(root)


def test_rejects_duplicate_source_ids(tmp_path: Path) -> None:
    root = tmp_path / "portfolio"
    content = root / "content"
    content.mkdir(parents=True)
    source_text = """\
schemaVersion: 1
sourceId: duplicate-project
sourceType: project
title: Duplicate
citationUrl: /projects/duplicate
content: Synthetic content.
visibility: public
"""
    (content / "one.yaml").write_text(source_text, encoding="utf-8")
    (content / "two.yaml").write_text(source_text, encoding="utf-8")
    (root / "folioaware.yaml").write_text(
        "schemaVersion: 1\nsources:\n"
        "  - path: content/one.yaml\n"
        "  - path: content/two.yaml\n",
        encoding="utf-8",
    )

    with pytest.raises(SyncValidationError, match="duplicate source ID"):
        load_approved_sources(root)
