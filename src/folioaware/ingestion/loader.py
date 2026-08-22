"""Load explicitly approved local source files through strict contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field

from folioaware.domain.base import DomainModel
from folioaware.domain.exceptions import SyncValidationError
from folioaware.domain.knowledge import ApprovedSource


class ManifestEntry(DomainModel):
    path: str = Field(min_length=1, max_length=500)


class PortfolioManifest(DomainModel):
    schema_version: int = Field(ge=1, le=1)
    sources: tuple[ManifestEntry, ...] = Field(min_length=1, max_length=1000)


def _load_mapping(path: Path) -> dict[str, Any]:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise SyncValidationError(
            f"unable to read approved source: {path.name}"
        ) from error

    try:
        parsed = (
            json.loads(raw_text)
            if path.suffix.lower() == ".json"
            else yaml.safe_load(raw_text)
        )
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        raise SyncValidationError(f"invalid approved source: {path.name}") from error

    if not isinstance(parsed, dict):
        raise SyncValidationError(f"approved source must be a mapping: {path.name}")
    return parsed


def _resolve_approved_path(content_root: Path, relative_value: str) -> Path:
    relative_path = Path(relative_value)
    if relative_path.is_absolute():
        raise SyncValidationError("approved source path must be repository-relative")

    root = content_root.resolve(strict=True)
    try:
        resolved = (root / relative_path).resolve(strict=True)
    except OSError as error:
        raise SyncValidationError("approved source path does not exist") from error

    if not resolved.is_relative_to(root):
        raise SyncValidationError("approved source path escapes the content root")
    if resolved.suffix.lower() not in {".json", ".yaml", ".yml"}:
        raise SyncValidationError(
            "local slice supports only JSON and safe YAML sources"
        )
    return resolved


def load_approved_sources(content_root: Path) -> tuple[ApprovedSource, ...]:
    """Load only files explicitly referenced by the root manifest."""
    manifest_path = content_root / "folioaware.yaml"
    try:
        manifest = PortfolioManifest.model_validate(_load_mapping(manifest_path))
    except ValueError as error:
        raise SyncValidationError("invalid folioaware.yaml manifest") from error

    sources: list[ApprovedSource] = []
    seen_ids: set[str] = set()
    for entry in manifest.sources:
        source_path = _resolve_approved_path(content_root, entry.path)
        try:
            source = ApprovedSource.model_validate(_load_mapping(source_path))
        except ValueError as error:
            raise SyncValidationError(
                f"approved source failed validation: {source_path.name}"
            ) from error
        if source.source_id in seen_ids:
            raise SyncValidationError(f"duplicate source ID: {source.source_id}")
        seen_ids.add(source.source_id)
        sources.append(source)

    return tuple(sources)
