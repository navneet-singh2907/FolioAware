from __future__ import annotations

from decimal import Decimal

from folioaware.domain.answers import AnswerStatus, Evidence
from folioaware.domain.knowledge import ApprovedSource, SourceType
from folioaware.evaluation.answer import AnswerObservation
from folioaware.evaluation.models import (
    EvaluationCase,
    EvaluationStatus,
    EvaluationSuite,
    EvaluationTag,
    RelevantPassage,
)
from folioaware.evaluation.report import (
    FailureReason,
    build_case_report,
    build_report,
    serialize_report,
    summarize_cases,
)
from folioaware.evaluation.retrieval import (
    RankedRetrievalCandidate,
    RetrievalCaseResult,
    RetrievalEvaluationResult,
    summarize_retrieval_cases,
)


def _case(case_id: str, *, answered: bool) -> EvaluationCase:
    return EvaluationCase(
        case_id=case_id,
        question=f"What happened in {case_id}?",
        expected_status=(
            EvaluationStatus.ANSWERED if answered else EvaluationStatus.KNOWLEDGE_GAP
        ),
        reference_answer="Supported passage." if answered else None,
        relevant_passages=(
            (RelevantPassage(source_id="source-a", text="Supported passage."),)
            if answered
            else ()
        ),
        required_citation_source_ids=("source-a",) if answered else (),
        tags=(
            (EvaluationTag.ANSWERABLE, EvaluationTag.PARAPHRASE)
            if answered
            else (EvaluationTag.UNANSWERABLE, EvaluationTag.WEAK_MATCH)
        ),
    )


def _retrieval(
    case: EvaluationCase,
    *,
    relevant: bool,
    eligible: bool = True,
) -> RetrievalCaseResult:
    candidate = RankedRetrievalCandidate(
        evidence_id=f"{case.case_id}-evidence",
        source_id="source-a" if relevant else "source-b",
        rank=1,
        distance=0.2 if eligible else 0.9,
        threshold_eligible=eligible,
        relevant=relevant,
    )
    return RetrievalCaseResult(
        case_id=case.case_id,
        expected_status=case.expected_status,
        candidates=(candidate,),
        hit=relevant,
        relevant_candidate_count=int(relevant),
        returned_candidate_count=1,
        context_relevance=Decimal(int(relevant)),
    )


def _observation(
    status: AnswerStatus,
    *,
    source_id: str | None = None,
) -> AnswerObservation:
    citations = (source_id,) if source_id is not None else ()
    evidence = (
        (
            Evidence(
                evidence_id="observed-evidence",
                source_id=source_id,
                content="Supported passage."
                if source_id == "source-a"
                else "Distractor.",
                citation_title="Synthetic source",
                citation_url="/synthetic",
                index_version="version-1",
                distance=0.2,
            ),
        )
        if source_id is not None
        else ()
    )
    return AnswerObservation(
        actual_status=status,
        citation_source_ids=citations,
        generation_call_count=int(status is AnswerStatus.ANSWERED),
        failure_code=None,
        eligible_evidence=evidence,
        answer=(
            evidence[0].content
            if status is AnswerStatus.ANSWERED and evidence
            else None
        ),
    )


def test_answer_metrics_cover_perfect_mixed_and_empty_boundaries() -> None:
    answerable_ok = _case("answerable-ok", answered=True)
    answerable_gap = _case("answerable-gap", answered=True)
    unanswerable_gap = _case("unanswerable-gap", answered=False)
    unanswerable_answer = _case("unanswerable-answer", answered=False)
    reports = (
        build_case_report(
            case=answerable_ok,
            retrieval=_retrieval(answerable_ok, relevant=True),
            observation=_observation(AnswerStatus.ANSWERED, source_id="source-a"),
        ),
        build_case_report(
            case=answerable_gap,
            retrieval=_retrieval(answerable_gap, relevant=True, eligible=False),
            observation=_observation(AnswerStatus.KNOWLEDGE_GAP),
        ),
        build_case_report(
            case=unanswerable_gap,
            retrieval=_retrieval(unanswerable_gap, relevant=False),
            observation=_observation(AnswerStatus.KNOWLEDGE_GAP),
        ),
        build_case_report(
            case=unanswerable_answer,
            retrieval=_retrieval(unanswerable_answer, relevant=False),
            observation=_observation(AnswerStatus.ANSWERED, source_id="source-b"),
        ),
    )

    metrics = summarize_cases(reports)

    assert metrics.correct_abstention_rate.value == Decimal("0.5")
    assert metrics.unsupported_answer_rate.value == Decimal("0.5")
    assert metrics.abstention_precision.value == Decimal("0.5")
    assert metrics.answer_coverage.value == Decimal("0.5")
    assert metrics.citation_membership.value == Decimal(1)
    assert metrics.citation_precision.value == Decimal("0.5")
    assert metrics.citation_recall.value == Decimal("0.5")
    assert metrics.extractive_support_rate.value == Decimal(1)
    assert summarize_cases(()).unsupported_answer_rate.value == Decimal(0)
    assert FailureReason.THRESHOLD_REJECTION in reports[1].failure_reasons
    assert FailureReason.OVER_ABSTENTION in reports[1].failure_reasons
    assert FailureReason.UNSUPPORTED_ANSWER in reports[3].failure_reasons
    assert FailureReason.IRRELEVANT_CITATION in reports[3].failure_reasons

    retrieval_miss = build_case_report(
        case=answerable_ok,
        retrieval=_retrieval(answerable_ok, relevant=False),
        observation=_observation(AnswerStatus.KNOWLEDGE_GAP),
    )
    assert FailureReason.RETRIEVAL_MISS in retrieval_miss.failure_reasons
    assert retrieval_miss.passed is False


def test_builds_stable_report_and_fails_closed_on_unsupported_answer() -> None:
    supported = _case("supported", answered=True)
    unsupported = _case("unsupported", answered=False)
    suite = EvaluationSuite(
        schema_version=1,
        suite_id="report-suite",
        description="Stable report test.",
        policy_version="evidence-policy-v1",
        cases=(supported, unsupported),
    )
    retrieval_cases = (
        _retrieval(supported, relevant=True),
        _retrieval(unsupported, relevant=False),
    )
    hit, context = summarize_retrieval_cases(retrieval_cases)
    retrieval = RetrievalEvaluationResult(
        top_k=1,
        distance_threshold=0.85,
        cases=retrieval_cases,
        hit_at_k=hit,
        context_relevance_at_k=context,
    )
    observations = (
        _observation(AnswerStatus.ANSWERED, source_id="source-a"),
        _observation(AnswerStatus.ANSWERED, source_id="source-b"),
    )
    source = ApprovedSource(
        schema_version=1,
        source_id="source-a",
        source_type=SourceType.PROJECT,
        title="Synthetic source",
        citation_url="/synthetic",
        content="Supported passage.",
    )

    report = build_report(
        suite=suite,
        sources=(source,),
        retrieval=retrieval,
        observations=observations,
        content_git_revision="abcdef1",
        embedding_model="local-test",
        embedding_dimensions=8,
        generator_id="local-extractive-v1",
        discarded_question_count=2,
    )

    first = serialize_report(report)
    second = serialize_report(report)
    assert first == second
    assert report.passed is False
    assert report.metrics.unsupported_answer_rate.value == Decimal(1)
    assert [item.tag.value for item in report.tag_metrics] == [
        "answerable",
        "paraphrase",
        "unanswerable",
        "weak-match",
    ]
    assert "requestId" not in first
    assert "createdAt" not in first
