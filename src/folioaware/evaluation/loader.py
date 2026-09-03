"""Safe loading and approved-source validation for evaluation suites."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from folioaware.domain.knowledge import ApprovedSource, Visibility
from folioaware.evaluation.models import (
    EvaluationSuite,
    normalize_evaluation_text,
)

MAXIMUM_SUITE_BYTES = 1_000_000


class EvaluationValidationError(ValueError):
    """Evaluation input is unsafe, malformed, or inconsistent with sources."""


def _load_mapping(path: Path) -> dict[str, Any]:
    if path.suffix.casefold() not in {".json", ".yaml", ".yml"}:
        raise EvaluationValidationError("evaluation suite must be JSON or YAML")

    try:
        payload = path.read_bytes()
    except OSError as error:
        raise EvaluationValidationError("unable to read evaluation suite") from error
    if len(payload) > MAXIMUM_SUITE_BYTES:
        raise EvaluationValidationError("evaluation suite exceeds size limit")

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EvaluationValidationError(
            "evaluation suite must be valid UTF-8"
        ) from error

    try:
        parsed = (
            json.loads(text)
            if path.suffix.casefold() == ".json"
            else yaml.safe_load(text)
        )
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        raise EvaluationValidationError("evaluation suite is malformed") from error
    if not isinstance(parsed, dict):
        raise EvaluationValidationError("evaluation suite must be a mapping")
    return parsed


def _validate_source_references(
    suite: EvaluationSuite, approved_sources: Sequence[ApprovedSource]
) -> None:
    sources_by_id = {source.source_id: source for source in approved_sources}
    if len(sources_by_id) != len(approved_sources):
        raise EvaluationValidationError("approved source IDs must be unique")

    normalized_content = {
        source_id: normalize_evaluation_text(source.content)
        for source_id, source in sources_by_id.items()
    }
    for case in suite.cases:
        for passage in case.relevant_passages:
            source_content = normalized_content.get(passage.source_id)
            if source_content is None:
                raise EvaluationValidationError(
                    f"case {case.case_id} references an unknown source"
                )
            if sources_by_id[passage.source_id].visibility is not Visibility.PUBLIC:
                raise EvaluationValidationError(
                    f"case {case.case_id} references a non-public source"
                )
            if passage.text not in source_content:
                raise EvaluationValidationError(
                    f"case {case.case_id} passage is absent from its source"
                )


def load_evaluation_suite(
    path: Path, *, approved_sources: Sequence[ApprovedSource]
) -> EvaluationSuite:
    """Load one strict suite and prove every positive label exists in evidence."""
    try:
        suite = EvaluationSuite.model_validate(_load_mapping(path))
    except ValidationError as error:
        raise EvaluationValidationError(
            "evaluation suite failed contract validation"
        ) from error
    _validate_source_references(suite, approved_sources)
    return suite
