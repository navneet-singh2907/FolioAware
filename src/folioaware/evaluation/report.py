"""Stable evaluation report contracts, scoring, gates, and serialization."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from pydantic import Field, model_validator

from folioaware.domain.answers import AnswerStatus
from folioaware.domain.base import DomainModel
from folioaware.domain.knowledge import ApprovedSource
from folioaware.evaluation.answer import AnswerObservation
from folioaware.evaluation.models import (
    EvaluationCase,
    EvaluationStatus,
    EvaluationSuite,
    EvaluationTag,
    normalize_evaluation_text,
)
from folioaware.evaluation.retrieval import (
    ContextRelevanceMetric,
    RatioMetric,
    RetrievalCaseResult,
    RetrievalEvaluationResult,
    summarize_retrieval_cases,
)

REPORT_SCHEMA_VERSION = 1
MAXIMUM_REPORT_BYTES = 5_000_000


class FailureReason(StrEnum):
    EXECUTION_FAILURE = "execution_failure"
    RETRIEVAL_MISS = "retrieval_miss"
    THRESHOLD_REJECTION = "threshold_rejection"
    OVER_ABSTENTION = "over_abstention"
    UNSUPPORTED_ANSWER = "unsupported_answer"
    UNEXPECTED_STATUS = "unexpected_status"
    ANSWERED_WITHOUT_CITATIONS = "answered_without_citations"
    KNOWLEDGE_GAP_WITH_CITATIONS = "knowledge_gap_with_citations"
    CITATION_NOT_RETRIEVED = "citation_not_retrieved"
    IRRELEVANT_CITATION = "irrelevant_citation"
    MISSING_REQUIRED_CITATION = "missing_required_citation"
    ANSWER_NOT_EXTRACTIVELY_SUPPORTED = "answer_not_extractively_supported"


class AnswerCaseDiagnostic(DomainModel):
    actual_status: AnswerStatus | None
    citation_source_ids: tuple[str, ...]
    generation_call_count: int = Field(ge=0)
    failure_code: str | None = Field(default=None, min_length=1, max_length=100)
    citation_membership: RatioMetric
    citation_precision: RatioMetric
    citation_recall: RatioMetric
    extractively_supported: bool | None


class EvaluationCaseReport(DomainModel):
    case_id: str = Field(min_length=1, max_length=100)
    tags: tuple[EvaluationTag, ...]
    expected_status: EvaluationStatus
    retrieval: RetrievalCaseResult
    answer: AnswerCaseDiagnostic
    failure_reasons: tuple[FailureReason, ...]
    passed: bool

    @model_validator(mode="after")
    def case_identity_is_consistent(self) -> EvaluationCaseReport:
        if self.case_id != self.retrieval.case_id:
            raise ValueError("retrieval diagnostic belongs to another case")
        if self.expected_status is not self.retrieval.expected_status:
            raise ValueError("retrieval diagnostic has another expected status")
        if self.passed is not (not self.failure_reasons):
            raise ValueError("case status must match failure reasons")
        return self


class EvaluationMetricSet(DomainModel):
    hit_at_k: RatioMetric
    context_relevance_at_k: ContextRelevanceMetric
    correct_abstention_rate: RatioMetric
    unsupported_answer_rate: RatioMetric
    abstention_precision: RatioMetric
    answer_coverage: RatioMetric
    citation_membership: RatioMetric
    citation_precision: RatioMetric
    citation_recall: RatioMetric
    extractive_support_rate: RatioMetric


class TagMetricSet(DomainModel):
    tag: EvaluationTag
    case_count: int = Field(ge=1)
    metrics: EvaluationMetricSet


class GateName(StrEnum):
    SUITE_SOURCE_VALIDATION = "suite_source_validation"
    CASE_EXECUTION = "case_execution"
    UNSUPPORTED_ANSWER_RATE = "unsupported_answer_rate"
    CITATION_MEMBERSHIP = "citation_membership"
    ANSWERED_RESPONSES_HAVE_CITATIONS = "answered_responses_have_citations"
    KNOWLEDGE_GAPS_HAVE_NO_CITATIONS = "knowledge_gaps_have_no_citations"
    EXTRACTIVE_SUPPORT = "extractive_support"
    EVALUATION_ISOLATION = "evaluation_isolation"


class GateResult(DomainModel):
    name: GateName
    passed: bool


class SuiteMetadata(DomainModel):
    schema_version: int = Field(ge=1)
    suite_id: str = Field(min_length=1, max_length=100)
    suite_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    policy_version: str = Field(min_length=1, max_length=100)
    case_count: int = Field(ge=1)


class EvaluationConfiguration(DomainModel):
    content_git_revision: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    content_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    embedding_model: str = Field(min_length=1, max_length=200)
    embedding_dimensions: int = Field(ge=1, le=2048)
    generator_id: str = Field(min_length=1, max_length=200)
    top_k: int = Field(ge=1)
    distance_threshold: float = Field(ge=0, le=2)


class BaselineComparison(DomainModel):
    baseline_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    failure_reasons: tuple[str, ...]
    passed: bool

    @model_validator(mode="after")
    def status_matches_reasons(self) -> BaselineComparison:
        if self.passed is not (not self.failure_reasons):
            raise ValueError("comparison status must match failure reasons")
        return self


class EvaluationReport(DomainModel):
    report_schema_version: int = Field(ge=1, le=REPORT_SCHEMA_VERSION)
    suite: SuiteMetadata
    configuration: EvaluationConfiguration
    metrics: EvaluationMetricSet
    tag_metrics: tuple[TagMetricSet, ...]
    cases: tuple[EvaluationCaseReport, ...]
    gates: tuple[GateResult, ...]
    baseline_comparison: BaselineComparison | None = None
    passed: bool

    @model_validator(mode="after")
    def overall_status_matches_gates(self) -> EvaluationReport:
        expected = all(gate.passed for gate in self.gates) and (
            self.baseline_comparison is None or self.baseline_comparison.passed
        )
        if self.passed is not expected:
            raise ValueError("overall status must match gates and baseline comparison")
        return self


def _ratio(numerator: int, denominator: int) -> RatioMetric:
    return RatioMetric(
        numerator=numerator,
        denominator=denominator,
        value=(
            Decimal(numerator) / Decimal(denominator) if denominator else Decimal(0)
        ),
    )


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def suite_digest(suite: EvaluationSuite) -> str:
    return _canonical_digest(suite.model_dump(mode="json", by_alias=True))


def approved_content_digest(sources: Sequence[ApprovedSource]) -> str:
    canonical_sources = [
        source.model_dump(mode="json", by_alias=True)
        for source in sorted(sources, key=lambda item: item.source_id)
    ]
    return _canonical_digest(canonical_sources)


def build_case_report(
    *,
    case: EvaluationCase,
    retrieval: RetrievalCaseResult,
    observation: AnswerObservation,
) -> EvaluationCaseReport:
    citations = observation.citation_source_ids
    eligible_sources = {
        evidence.source_id for evidence in observation.eligible_evidence
    }
    relevant_sources = {passage.source_id for passage in case.relevant_passages}
    required_sources = set(case.required_citation_source_ids)
    cited_sources = set(citations)
    membership_hits = sum(source_id in eligible_sources for source_id in citations)
    precision_hits = sum(source_id in relevant_sources for source_id in citations)
    recall_hits = len(required_sources.intersection(cited_sources))
    extractively_supported = _is_extractively_supported(observation)

    answer = AnswerCaseDiagnostic(
        actual_status=observation.actual_status,
        citation_source_ids=citations,
        generation_call_count=observation.generation_call_count,
        failure_code=observation.failure_code,
        citation_membership=_ratio(membership_hits, len(citations)),
        citation_precision=_ratio(precision_hits, len(citations)),
        citation_recall=_ratio(recall_hits, len(required_sources)),
        extractively_supported=extractively_supported,
    )
    failure_reasons = _failure_reasons(case, retrieval, answer)
    return EvaluationCaseReport(
        case_id=case.case_id,
        tags=case.tags,
        expected_status=case.expected_status,
        retrieval=retrieval,
        answer=answer,
        failure_reasons=failure_reasons,
        passed=not failure_reasons,
    )


def _is_extractively_supported(observation: AnswerObservation) -> bool | None:
    if observation.actual_status is not AnswerStatus.ANSWERED:
        return None
    if observation.answer is None:
        return False
    return any(
        evidence.source_id in observation.citation_source_ids
        and observation.answer in normalize_evaluation_text(evidence.content)
        for evidence in observation.eligible_evidence
    )


def _failure_reasons(
    case: EvaluationCase,
    retrieval: RetrievalCaseResult,
    answer: AnswerCaseDiagnostic,
) -> tuple[FailureReason, ...]:
    reasons: list[FailureReason] = []
    actual = answer.actual_status
    relevant_eligible = any(
        candidate.relevant and candidate.threshold_eligible
        for candidate in retrieval.candidates
    )
    if answer.failure_code is not None:
        reasons.append(FailureReason.EXECUTION_FAILURE)
    if case.expected_status is EvaluationStatus.ANSWERED and not retrieval.hit:
        reasons.append(FailureReason.RETRIEVAL_MISS)
    if (
        case.expected_status is EvaluationStatus.ANSWERED
        and retrieval.hit
        and not relevant_eligible
    ):
        reasons.append(FailureReason.THRESHOLD_REJECTION)
    if (
        case.expected_status is EvaluationStatus.ANSWERED
        and actual is AnswerStatus.KNOWLEDGE_GAP
    ):
        reasons.append(FailureReason.OVER_ABSTENTION)
    if (
        case.expected_status is EvaluationStatus.KNOWLEDGE_GAP
        and actual is AnswerStatus.ANSWERED
    ):
        reasons.append(FailureReason.UNSUPPORTED_ANSWER)
    if actual is AnswerStatus.PARTIAL:
        reasons.append(FailureReason.UNEXPECTED_STATUS)
    if actual is AnswerStatus.ANSWERED and not answer.citation_source_ids:
        reasons.append(FailureReason.ANSWERED_WITHOUT_CITATIONS)
    if actual is AnswerStatus.KNOWLEDGE_GAP and answer.citation_source_ids:
        reasons.append(FailureReason.KNOWLEDGE_GAP_WITH_CITATIONS)
    if answer.citation_membership.numerator < answer.citation_membership.denominator:
        reasons.append(FailureReason.CITATION_NOT_RETRIEVED)
    if answer.citation_precision.numerator < answer.citation_precision.denominator:
        reasons.append(FailureReason.IRRELEVANT_CITATION)
    if answer.citation_recall.numerator < answer.citation_recall.denominator:
        reasons.append(FailureReason.MISSING_REQUIRED_CITATION)
    if answer.extractively_supported is False:
        reasons.append(FailureReason.ANSWER_NOT_EXTRACTIVELY_SUPPORTED)
    return tuple(reasons)


def summarize_cases(cases: Sequence[EvaluationCaseReport]) -> EvaluationMetricSet:
    selected = tuple(cases)
    retrieval_cases = tuple(case.retrieval for case in selected)
    hit_at_k, context_relevance_at_k = summarize_retrieval_cases(retrieval_cases)
    answerable = tuple(
        case for case in selected if case.expected_status is EvaluationStatus.ANSWERED
    )
    unanswerable = tuple(
        case
        for case in selected
        if case.expected_status is EvaluationStatus.KNOWLEDGE_GAP
    )
    predicted_gaps = tuple(
        case
        for case in selected
        if case.answer.actual_status is AnswerStatus.KNOWLEDGE_GAP
    )
    answered = tuple(
        case for case in selected if case.answer.actual_status is AnswerStatus.ANSWERED
    )
    correct_abstentions = sum(
        case.answer.actual_status is AnswerStatus.KNOWLEDGE_GAP for case in unanswerable
    )
    unsupported_answers = sum(
        case.answer.actual_status is AnswerStatus.ANSWERED for case in unanswerable
    )
    covered_answers = sum(
        case.answer.actual_status is AnswerStatus.ANSWERED for case in answerable
    )
    return EvaluationMetricSet(
        hit_at_k=hit_at_k,
        context_relevance_at_k=context_relevance_at_k,
        correct_abstention_rate=_ratio(correct_abstentions, len(unanswerable)),
        unsupported_answer_rate=_ratio(unsupported_answers, len(unanswerable)),
        abstention_precision=_ratio(correct_abstentions, len(predicted_gaps)),
        answer_coverage=_ratio(covered_answers, len(answerable)),
        citation_membership=_sum_case_ratios(
            selected, lambda answer: answer.citation_membership
        ),
        citation_precision=_sum_case_ratios(
            selected, lambda answer: answer.citation_precision
        ),
        citation_recall=_sum_case_ratios(
            selected, lambda answer: answer.citation_recall
        ),
        extractive_support_rate=_ratio(
            sum(case.answer.extractively_supported is True for case in answered),
            len(answered),
        ),
    )


def _sum_case_ratios(
    cases: Sequence[EvaluationCaseReport],
    select: Callable[[AnswerCaseDiagnostic], RatioMetric],
) -> RatioMetric:
    values = [select(case.answer) for case in cases]
    return _ratio(
        sum(value.numerator for value in values),
        sum(value.denominator for value in values),
    )


def build_report(
    *,
    suite: EvaluationSuite,
    sources: Sequence[ApprovedSource],
    retrieval: RetrievalEvaluationResult,
    observations: Sequence[AnswerObservation],
    content_git_revision: str,
    embedding_model: str,
    embedding_dimensions: int,
    generator_id: str,
    discarded_question_count: int,
) -> EvaluationReport:
    if len(suite.cases) != len(retrieval.cases) or len(suite.cases) != len(
        observations
    ):
        raise ValueError("evaluation planes must contain every suite case")
    case_reports = tuple(
        build_case_report(case=case, retrieval=retrieval_case, observation=observation)
        for case, retrieval_case, observation in zip(
            suite.cases, retrieval.cases, observations, strict=True
        )
    )
    metrics = summarize_cases(case_reports)
    tag_values = sorted(
        {tag for case in suite.cases for tag in case.tags}, key=lambda tag: tag.value
    )
    tag_metrics = tuple(
        TagMetricSet(
            tag=tag,
            case_count=sum(tag in case.tags for case in case_reports),
            metrics=summarize_cases(
                tuple(case for case in case_reports if tag in case.tags)
            ),
        )
        for tag in tag_values
    )
    answered = tuple(
        case
        for case in case_reports
        if case.answer.actual_status is AnswerStatus.ANSWERED
    )
    gaps = tuple(
        case
        for case in case_reports
        if case.answer.actual_status is AnswerStatus.KNOWLEDGE_GAP
    )
    gates = (
        GateResult(name=GateName.SUITE_SOURCE_VALIDATION, passed=True),
        GateResult(
            name=GateName.CASE_EXECUTION,
            passed=all(
                case.answer.failure_code is None
                and case.answer.actual_status
                in {AnswerStatus.ANSWERED, AnswerStatus.KNOWLEDGE_GAP}
                for case in case_reports
            ),
        ),
        GateResult(
            name=GateName.UNSUPPORTED_ANSWER_RATE,
            passed=metrics.unsupported_answer_rate.numerator == 0,
        ),
        GateResult(
            name=GateName.CITATION_MEMBERSHIP,
            passed=(
                metrics.citation_membership.numerator
                == metrics.citation_membership.denominator
            ),
        ),
        GateResult(
            name=GateName.ANSWERED_RESPONSES_HAVE_CITATIONS,
            passed=all(case.answer.citation_source_ids for case in answered),
        ),
        GateResult(
            name=GateName.KNOWLEDGE_GAPS_HAVE_NO_CITATIONS,
            passed=all(not case.answer.citation_source_ids for case in gaps),
        ),
        GateResult(
            name=GateName.EXTRACTIVE_SUPPORT,
            passed=(
                metrics.extractive_support_rate.numerator
                == metrics.extractive_support_rate.denominator
            ),
        ),
        GateResult(
            name=GateName.EVALUATION_ISOLATION,
            passed=discarded_question_count == len(case_reports),
        ),
    )
    return EvaluationReport(
        report_schema_version=REPORT_SCHEMA_VERSION,
        suite=SuiteMetadata(
            schema_version=suite.schema_version,
            suite_id=suite.suite_id,
            suite_digest=suite_digest(suite),
            policy_version=suite.policy_version,
            case_count=len(suite.cases),
        ),
        configuration=EvaluationConfiguration(
            content_git_revision=content_git_revision,
            content_digest=approved_content_digest(sources),
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
            generator_id=generator_id,
            top_k=retrieval.top_k,
            distance_threshold=retrieval.distance_threshold,
        ),
        metrics=metrics,
        tag_metrics=tag_metrics,
        cases=case_reports,
        gates=gates,
        passed=all(gate.passed for gate in gates),
    )


def serialize_report(report: EvaluationReport) -> str:
    """Return byte-stable compact JSON without a platform-specific newline."""
    return json.dumps(
        report.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def load_report(path: Path) -> EvaluationReport:
    """Load one bounded, strict baseline report without trusting its contents."""
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise ValueError("unable to read evaluation baseline") from error
    if len(payload) > MAXIMUM_REPORT_BYTES:
        raise ValueError("evaluation baseline exceeds size limit")
    try:
        return EvaluationReport.model_validate_json(payload)
    except ValueError as error:
        raise ValueError("evaluation baseline failed validation") from error


def compare_with_baseline(
    current: EvaluationReport, baseline: EvaluationReport
) -> BaselineComparison:
    """Require compatible inputs, passing gates, and no metric regression."""
    reasons: list[str] = []
    if baseline.baseline_comparison is not None or not baseline.passed:
        reasons.append("invalid_baseline")
    if current.report_schema_version != baseline.report_schema_version:
        reasons.append("report_schema_changed")
    if current.suite != baseline.suite:
        reasons.append("suite_changed")
    if current.configuration != baseline.configuration:
        reasons.append("configuration_changed")
    reasons.extend(
        f"hard_gate_failed:{gate.name.value}"
        for gate in current.gates
        if not gate.passed
    )
    reasons.extend(_metric_regressions(current.metrics, baseline.metrics, "aggregate"))

    current_tags = {item.tag: item for item in current.tag_metrics}
    baseline_tags = {item.tag: item for item in baseline.tag_metrics}
    if current_tags.keys() != baseline_tags.keys():
        reasons.append("tag_partitions_changed")
    else:
        for tag in sorted(current_tags, key=lambda item: item.value):
            current_tag = current_tags[tag]
            baseline_tag = baseline_tags[tag]
            if current_tag.case_count != baseline_tag.case_count:
                reasons.append(f"tag_case_count_changed:{tag.value}")
                continue
            reasons.extend(
                _metric_regressions(
                    current_tag.metrics,
                    baseline_tag.metrics,
                    f"tag:{tag.value}",
                )
            )

    unique_reasons = tuple(dict.fromkeys(reasons))
    return BaselineComparison(
        baseline_digest=_canonical_digest(
            baseline.model_dump(mode="json", by_alias=True)
        ),
        failure_reasons=unique_reasons,
        passed=not unique_reasons,
    )


def _metric_regressions(
    current: EvaluationMetricSet,
    baseline: EvaluationMetricSet,
    scope: str,
) -> tuple[str, ...]:
    higher_is_better = (
        "hit_at_k",
        "context_relevance_at_k",
        "correct_abstention_rate",
        "abstention_precision",
        "answer_coverage",
        "citation_membership",
        "citation_precision",
        "citation_recall",
        "extractive_support_rate",
    )
    regressions = [
        f"metric_regressed:{scope}:{name}"
        for name in higher_is_better
        if getattr(current, name).value < getattr(baseline, name).value
    ]
    if current.unsupported_answer_rate.value > baseline.unsupported_answer_rate.value:
        regressions.append(f"metric_regressed:{scope}:unsupported_answer_rate")
    return tuple(regressions)


def attach_baseline_comparison(
    report: EvaluationReport, comparison: BaselineComparison
) -> EvaluationReport:
    payload = report.model_dump(mode="python")
    payload["baseline_comparison"] = comparison
    payload["passed"] = report.passed and comparison.passed
    return EvaluationReport.model_validate(payload)
