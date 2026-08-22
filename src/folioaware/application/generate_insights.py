"""Aggregate sanitized questions into non-evidentiary owner recommendations."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from folioaware.domain.answers import AnswerStatus
from folioaware.domain.telemetry import (
    InsightReport,
    QuestionIntent,
    SuggestedAction,
    TopicInsight,
)
from folioaware.ports.analytics import (
    InsightRepository,
    QuestionClassifier,
    QuestionTelemetryReader,
)
from folioaware.ports.runtime import Clock


@dataclass(slots=True)
class _Counts:
    questions: int = 0
    gaps: int = 0
    skill_verifications: int = 0
    sessions: set[str] = field(default_factory=set)


class GenerateInsightReport:
    def __init__(
        self,
        *,
        questions: QuestionTelemetryReader,
        classifier: QuestionClassifier,
        insights: InsightRepository,
        clock: Clock,
        minimum_question_count: int,
    ) -> None:
        if minimum_question_count < 2:
            raise ValueError("repeated-topic threshold must be at least two")
        self._questions = questions
        self._classifier = classifier
        self._insights = insights
        self._clock = clock
        self._minimum_question_count = minimum_question_count

    def execute(self, *, period_start: datetime, period_end: datetime) -> InsightReport:
        if period_end <= period_start:
            raise ValueError("report period end must follow its start")
        generated_at = self._clock.now()
        records = tuple(
            record
            for record in self._questions.list_between(
                period_start=period_start, period_end=period_end
            )
            if record.expires_at > generated_at
        )
        counts: dict[str, _Counts] = defaultdict(_Counts)
        for record in records:
            classified = self._classifier.classify(record.redacted_question)
            for topic in classified.topics:
                item = counts[topic]
                item.questions += 1
                if record.answer_status is AnswerStatus.KNOWLEDGE_GAP:
                    item.gaps += 1
                if classified.intent is QuestionIntent.SKILL_VERIFICATION:
                    item.skill_verifications += 1
                if record.session_hash is not None:
                    item.sessions.add(record.session_hash)

        results = tuple(
            TopicInsight(
                insight_id=self._insight_id(topic, period_start, period_end),
                topic=topic,
                period_start=period_start,
                period_end=period_end,
                distinct_session_count=len(item.sessions),
                question_count=item.questions,
                skill_verification_count=item.skill_verifications,
                knowledge_gap_count=item.gaps,
                suggested_action=self._suggest_action(item),
                created_at=generated_at,
            )
            for topic, item in sorted(counts.items())
            if item.questions >= self._minimum_question_count
        )
        self._insights.replace_period(
            period_start=period_start,
            period_end=period_end,
            insights=results,
        )
        return InsightReport(
            period_start=period_start,
            period_end=period_end,
            generated_at=generated_at,
            minimum_question_count=self._minimum_question_count,
            analyzed_question_count=len(records),
            insights=results,
        )

    @staticmethod
    def _insight_id(topic: str, start: datetime, end: datetime) -> str:
        return f"{topic}:{start.isoformat()}:{end.isoformat()}"

    @staticmethod
    def _suggest_action(counts: _Counts) -> SuggestedAction:
        if counts.gaps == 0:
            return SuggestedAction.LEAVE_UNAVAILABLE
        if counts.gaps == counts.questions and counts.skill_verifications > 0:
            return SuggestedAction.BUILD_PROJECT
        return SuggestedAction.ADD_EXISTING_EVIDENCE
