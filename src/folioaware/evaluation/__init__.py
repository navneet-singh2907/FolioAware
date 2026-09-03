"""Versioned, offline evaluation-suite contracts and loading."""

from folioaware.evaluation.loader import (
    EvaluationValidationError,
    load_evaluation_suite,
)
from folioaware.evaluation.models import (
    EvaluationCase,
    EvaluationStatus,
    EvaluationSuite,
    EvaluationTag,
    RelevantPassage,
)

__all__ = [
    "EvaluationCase",
    "EvaluationStatus",
    "EvaluationSuite",
    "EvaluationTag",
    "EvaluationValidationError",
    "RelevantPassage",
    "load_evaluation_suite",
]
