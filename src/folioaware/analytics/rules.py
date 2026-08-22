"""Strict loader for owner-maintained telemetry topic aliases."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter, ValidationError

from folioaware.domain.telemetry import TopicRule

_RULES_ADAPTER = TypeAdapter(tuple[TopicRule, ...])


def load_topic_rules(path: Path) -> tuple[TopicRule, ...]:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError("topic rule file could not be loaded") from error
    if not isinstance(raw, dict) or set(raw) != {"topics"}:
        raise ValueError("topic rule file must contain only a topics field")
    try:
        rules = _RULES_ADAPTER.validate_python(raw["topics"])
    except ValidationError as error:
        raise ValueError("topic rule file is invalid") from error
    topics = [rule.topic for rule in rules]
    if len(rules) > 100:
        raise ValueError("topic rule file cannot exceed 100 topics")
    if len(set(topics)) != len(topics):
        raise ValueError("topic rules must use unique topic names")
    return rules
