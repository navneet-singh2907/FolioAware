from datetime import UTC, datetime

import pytest

from folioaware.api.dependencies import build_local_container
from folioaware.application.answer_question import AnswerQuestion
from folioaware.domain.answers import AnswerCandidate, GenerationRequest
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
            answer="An invented claim that is not present in the evidence.",
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


@pytest.mark.parametrize("mode", ["unknown", "duplicate", "invented"])
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
