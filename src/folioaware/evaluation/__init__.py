"""Versioned, offline evaluation-suite contracts and loading."""

from folioaware.evaluation.answer import (
    AnswerEvaluator,
    AnswerObservation,
    DiscardQuestionRepository,
    RecordingKnowledgeRepository,
)
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
from folioaware.evaluation.report import (
    BaselineComparison,
    EvaluationReport,
    FailureReason,
    attach_baseline_comparison,
    compare_with_baseline,
    load_report,
    serialize_report,
)
from folioaware.evaluation.retrieval import (
    ContextRelevanceMetric,
    RankedRetrievalCandidate,
    RatioMetric,
    RetrievalCaseResult,
    RetrievalEvaluationResult,
    RetrievalEvaluator,
    candidate_is_relevant,
    summarize_retrieval_cases,
)
from folioaware.evaluation.runner import OfflineEvaluationRunner

__all__ = [
    "AnswerEvaluator",
    "AnswerObservation",
    "BaselineComparison",
    "ContextRelevanceMetric",
    "DiscardQuestionRepository",
    "EvaluationCase",
    "EvaluationReport",
    "EvaluationStatus",
    "EvaluationSuite",
    "EvaluationTag",
    "EvaluationValidationError",
    "FailureReason",
    "OfflineEvaluationRunner",
    "RankedRetrievalCandidate",
    "RatioMetric",
    "RecordingKnowledgeRepository",
    "RelevantPassage",
    "RetrievalCaseResult",
    "RetrievalEvaluationResult",
    "RetrievalEvaluator",
    "attach_baseline_comparison",
    "candidate_is_relevant",
    "compare_with_baseline",
    "load_evaluation_suite",
    "load_report",
    "serialize_report",
    "summarize_retrieval_cases",
]
