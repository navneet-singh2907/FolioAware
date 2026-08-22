from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from folioaware.adapters.local import (
    InMemoryInsightRepository,
    InMemoryQuestionRepository,
)
from folioaware.analytics import DeterministicQuestionClassifier, load_topic_rules
from folioaware.application.generate_insights import GenerateInsightReport
from folioaware.domain.answers import AnswerStatus
from folioaware.domain.telemetry import (
    QuestionIntent,
    SuggestedAction,
    TopicRule,
    VisitorQuestion,
)

NOW = datetime(2026, 8, 24, 1, tzinfo=UTC)
START = datetime(2026, 8, 17, tzinfo=UTC)
END = datetime(2026, 8, 24, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


def question(
    identifier: str,
    text: str,
    *,
    status: AnswerStatus = AnswerStatus.KNOWLEDGE_GAP,
    session: str | None = None,
    created_at: datetime = START + timedelta(days=1),
) -> VisitorQuestion:
    return VisitorQuestion(
        question_id=identifier,
        redacted_question=text,
        session_hash=session,
        answer_status=status,
        knowledge_version="version-1",
        created_at=created_at,
        expires_at=created_at + timedelta(days=90),
    )


def classifier() -> DeterministicQuestionClassifier:
    return DeterministicQuestionClassifier(
        (
            TopicRule(topic="apache-kafka", aliases=("kafka", "apache kafka")),
            TopicRule(topic="fastapi", aliases=("fastapi",)),
        )
    )


def test_classifier_explains_topics_and_skill_verification() -> None:
    result = classifier().classify("Has this developer worked with Apache Kafka?")

    assert result.topics == ("apache-kafka",)
    assert result.intent is QuestionIntent.SKILL_VERIFICATION
    assert classifier().classify("Is Kafkaesque a word?").topics == ()


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("What architecture uses FastAPI?", QuestionIntent.ARCHITECTURE),
        ("Which project implemented FastAPI?", QuestionIntent.PROJECT_EXPERIENCE),
        ("Is the developer available?", QuestionIntent.AVAILABILITY),
        ("Tell me about FastAPI", QuestionIntent.UNKNOWN),
    ],
)
def test_classifier_intent_rules_are_deterministic(
    text: str, intent: QuestionIntent
) -> None:
    assert classifier().classify(text).intent is intent


def test_repeated_gap_topic_produces_non_evidentiary_owner_nudge() -> None:
    questions = InMemoryQuestionRepository()
    questions.save(question("q1", "Have they used Kafka?", session="session-a"))
    questions.save(question("q2", "Did they work with Kafka?", session="session-a"))
    questions.save(question("q3", "Do they know Apache Kafka?", session="session-b"))
    questions.save(
        question(
            "outside",
            "Have they used Kafka?",
            created_at=END,
            session="session-c",
        )
    )
    insights = InMemoryInsightRepository()
    service = GenerateInsightReport(
        questions=questions,
        classifier=classifier(),
        insights=insights,
        clock=FixedClock(),
        minimum_question_count=2,
    )

    report = service.execute(period_start=START, period_end=END)

    assert report.analyzed_question_count == 3
    assert len(report.insights) == 1
    kafka = report.insights[0]
    assert kafka.question_count == 3
    assert kafka.distinct_session_count == 2
    assert kafka.skill_verification_count == 3
    assert kafka.knowledge_gap_count == 3
    assert kafka.suggested_action is SuggestedAction.BUILD_PROJECT
    assert insights.records[kafka.insight_id] == kafka


def test_single_occurrence_is_not_reported_and_replaces_old_period() -> None:
    questions = InMemoryQuestionRepository()
    questions.save(question("q1", "Was FastAPI used?"))
    insights = InMemoryInsightRepository()
    service = GenerateInsightReport(
        questions=questions,
        classifier=classifier(),
        insights=insights,
        clock=FixedClock(),
        minimum_question_count=2,
    )

    report = service.execute(period_start=START, period_end=END)

    assert report.insights == ()
    assert insights.records == {}


def test_expired_telemetry_is_not_analyzed() -> None:
    questions = InMemoryQuestionRepository()
    expired_created = NOW - timedelta(days=100)
    questions.save(
        VisitorQuestion(
            question_id="expired-1",
            redacted_question="Have they used Kafka?",
            answer_status=AnswerStatus.KNOWLEDGE_GAP,
            knowledge_version="version-1",
            created_at=expired_created,
            expires_at=NOW - timedelta(days=1),
        )
    )
    service = GenerateInsightReport(
        questions=questions,
        classifier=classifier(),
        insights=InMemoryInsightRepository(),
        clock=FixedClock(),
        minimum_question_count=2,
    )

    report = service.execute(period_start=NOW - timedelta(days=120), period_end=NOW)

    assert report.analyzed_question_count == 0


def test_suggestion_policy_distinguishes_mixed_and_answered_results() -> None:
    questions = InMemoryQuestionRepository()
    questions.save(question("q1", "Have they used Kafka?"))
    questions.save(
        question(
            "q2",
            "Did they work with Kafka?",
            status=AnswerStatus.ANSWERED,
        )
    )
    questions.save(question("q3", "Was FastAPI used?", status=AnswerStatus.ANSWERED))
    questions.save(
        question("q4", "Did they work with FastAPI?", status=AnswerStatus.ANSWERED)
    )
    service = GenerateInsightReport(
        questions=questions,
        classifier=classifier(),
        insights=InMemoryInsightRepository(),
        clock=FixedClock(),
        minimum_question_count=2,
    )

    report = service.execute(period_start=START, period_end=END)

    actions = {item.topic: item.suggested_action for item in report.insights}
    assert actions == {
        "apache-kafka": SuggestedAction.ADD_EXISTING_EVIDENCE,
        "fastapi": SuggestedAction.LEAVE_UNAVAILABLE,
    }


def test_aggregation_rejects_non_repeated_threshold_and_invalid_period() -> None:
    with pytest.raises(ValueError, match="at least two"):
        GenerateInsightReport(
            questions=InMemoryQuestionRepository(),
            classifier=classifier(),
            insights=InMemoryInsightRepository(),
            clock=FixedClock(),
            minimum_question_count=1,
        )
    service = GenerateInsightReport(
        questions=InMemoryQuestionRepository(),
        classifier=classifier(),
        insights=InMemoryInsightRepository(),
        clock=FixedClock(),
        minimum_question_count=2,
    )
    with pytest.raises(ValueError, match="period end"):
        service.execute(period_start=END, period_end=START)


def test_rule_loader_accepts_synthetic_fixture_and_rejects_unknown_fields(
    tmp_path: Path,
) -> None:
    rules = load_topic_rules(Path("examples/synthetic-portfolio/insight-topics.yaml"))
    assert {rule.topic for rule in rules} >= {"apache-kafka", "fastapi"}

    invalid = tmp_path / "invalid-topics.yaml"
    invalid.write_text("topics: []\nuntrusted: true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="only a topics field"):
        load_topic_rules(invalid)

    duplicate = tmp_path / "duplicate-topics.yaml"
    duplicate.write_text(
        "topics:\n  - topic: kafka\n    aliases: [kafka]\n"
        "  - topic: kafka\n    aliases: [apache-kafka]\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unique topic"):
        load_topic_rules(duplicate)

    malformed = tmp_path / "malformed-topics.yaml"
    malformed.write_text("topics: [", encoding="utf-8")
    with pytest.raises(ValueError, match="could not be loaded"):
        load_topic_rules(malformed)
