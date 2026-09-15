from datetime import UTC, datetime

import pytest

from folioaware.api.dependencies import build_local_container
from folioaware.application.answer_question import AnswerQuestion
from folioaware.domain.answers import AnswerCandidate, AnswerStatus, GenerationRequest
from folioaware.domain.exceptions import InvalidModelOutputError
from folioaware.ports.question_repository import QuestionRepository
from folioaware.security import TelemetrySanitizer


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 22, tzinfo=UTC)


class FixedIdentifiers:
    def new(self) -> str:
        return "request-1"


class InvalidGenerator:
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def generate(self, request: GenerationRequest) -> AnswerCandidate:
        evidence = request.evidence[0]
        if self.mode == "abstain":
            return AnswerCandidate(
                answer="Untrusted model text should not escape on abstention.",
                evidence_ids=(),
                answer_status=AnswerStatus.KNOWLEDGE_GAP,
            )
        if self.mode == "unknown":
            return AnswerCandidate(
                answer=evidence.content,
                evidence_ids=("not-retrieved",),
            )
        if self.mode == "duplicate":
            return AnswerCandidate(
                answer=evidence.content,
                evidence_ids=(evidence.evidence_id, evidence.evidence_id),
            )
        if self.mode == "extract":
            answer = next(
                line.strip()
                for line in evidence.content.splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
            return AnswerCandidate(
                answer=answer,
                evidence_ids=(evidence.evidence_id,),
            )
        return AnswerCandidate(
            answer="Yes, Project Atlas uses FastAPI for its API.",
            evidence_ids=(evidence.evidence_id,),
        )


class FailingQuestionRepository:
    def save(self, _question: object) -> None:
        raise RuntimeError("simulated telemetry outage")


def build_service(
    generator: InvalidGenerator,
    questions: QuestionRepository | None = None,
) -> AnswerQuestion:
    container = build_local_container()
    return AnswerQuestion(
        embeddings=container.embeddings,
        generation=generator,
        knowledge=container.knowledge,
        questions=questions or container.questions,
        sanitizer=TelemetrySanitizer("test-secret-at-least-16-characters"),
        clock=FixedClock(),
        identifiers=FixedIdentifiers(),
        distance_threshold=0.85,
        top_k=5,
        retention_days=30,
    )


@pytest.mark.parametrize("mode", ["unknown", "duplicate"])
def test_rejects_untrusted_generator_output(mode: str) -> None:
    service = build_service(InvalidGenerator(mode))

    with pytest.raises(InvalidModelOutputError):
        service.execute(question="Did they use FastAPI?", session_id=None)


def test_accepts_verbatim_extract_from_larger_cited_evidence() -> None:
    service = build_service(InvalidGenerator("extract"))

    result = service.execute(question="Did they use FastAPI?", session_id=None)

    assert result.answer_status == "answered"
    assert result.answer
    assert result.citations


def test_accepts_synthesis_with_application_owned_citations() -> None:
    service = build_service(InvalidGenerator("paraphrase"))

    result = service.execute(question="Did they use FastAPI?", session_id=None)

    assert result.answer == "Yes, Project Atlas uses FastAPI for its API."
    assert result.answer_status == "answered"
    assert len(result.citations) == 1
    assert "atlas" in result.citations[0].source_id


def test_generation_abstention_uses_trusted_text_and_no_citations() -> None:
    service = build_service(InvalidGenerator("abstain"))

    result = service.execute(question="Did they use FastAPI?", session_id=None)

    assert result.answer == "I don't have verified information about that."
    assert result.answer_status == "knowledge_gap"
    assert result.citations == ()


def test_telemetry_failure_does_not_break_a_verified_answer() -> None:
    container = build_local_container()
    service = AnswerQuestion(
        embeddings=container.embeddings,
        generation=container.generation,
        knowledge=container.knowledge,
        questions=FailingQuestionRepository(),
        sanitizer=TelemetrySanitizer("test-secret-at-least-16-characters"),
        clock=FixedClock(),
        identifiers=FixedIdentifiers(),
        distance_threshold=0.85,
        top_k=5,
        retention_days=30,
    )

    result = service.execute(question="Did they use FastAPI?", session_id=None)

    assert result.answer_status == "answered"


def test_follow_up_query_includes_one_prior_question_without_exceeding_limit() -> None:
    contextual_question = AnswerQuestion._contextual_question(
        "Which project used it?",
        "Did Navneet use Terraform?",
    )

    assert contextual_question == (
        "Previous question: Did Navneet use Terraform? "
        "Follow-up question: Which project used it?"
    )
    assert (
        AnswerQuestion._contextual_question("x" * 500, "Did Navneet use Terraform?")
        == "x" * 500
    )
