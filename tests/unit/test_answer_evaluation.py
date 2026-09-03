from pathlib import Path

from folioaware.api.dependencies import build_local_container
from folioaware.application.answer_question import AnswerQuestion
from folioaware.domain.answers import AnswerCandidate, AnswerStatus, GenerationRequest
from folioaware.evaluation import (
    AnswerEvaluator,
    DiscardQuestionRepository,
    EvaluationCase,
    RecordingKnowledgeRepository,
    load_evaluation_suite,
)
from folioaware.ingestion import load_approved_sources
from folioaware.security import TelemetrySanitizer

CONTENT_ROOT = Path("examples/synthetic-portfolio")
SUITE_PATH = Path("evals/fixtures/synthetic-portfolio-v1.yaml")


class InvalidGenerationProvider:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, _request: GenerationRequest) -> AnswerCandidate:
        self.calls += 1
        return AnswerCandidate(
            answer="Invented output absent from evidence.",
            evidence_ids=("not-retrieved",),
        )


def _first_case() -> EvaluationCase:
    sources = load_approved_sources(CONTENT_ROOT)
    return load_evaluation_suite(SUITE_PATH, approved_sources=sources).cases[0]


def test_answer_evaluator_discards_successful_question_telemetry() -> None:
    container = build_local_container(content_root=CONTENT_ROOT)
    knowledge = RecordingKnowledgeRepository(container.knowledge)
    discard = DiscardQuestionRepository()
    answer_question = AnswerQuestion(
        embeddings=container.embeddings,
        generation=container.generation,
        knowledge=knowledge,
        questions=discard,
        sanitizer=TelemetrySanitizer("offline-evaluation-only"),
        clock=container.clock,
        identifiers=container.identifiers,
        distance_threshold=0.85,
        top_k=5,
        retention_days=1,
    )

    observation = AnswerEvaluator(
        answer_question=answer_question,
        knowledge=knowledge,
        generation=container.generation,
        distance_threshold=0.85,
    ).run_case(_first_case())

    assert observation.actual_status is AnswerStatus.ANSWERED
    assert observation.generation_call_count == 1
    assert discard.discarded_count == 1
    assert not hasattr(discard, "records")


def test_answer_evaluator_sanitizes_invalid_model_output() -> None:
    container = build_local_container(content_root=CONTENT_ROOT)
    knowledge = RecordingKnowledgeRepository(container.knowledge)
    discard = DiscardQuestionRepository()
    generation = InvalidGenerationProvider()
    answer_question = AnswerQuestion(
        embeddings=container.embeddings,
        generation=generation,
        knowledge=knowledge,
        questions=discard,
        sanitizer=TelemetrySanitizer("offline-evaluation-only"),
        clock=container.clock,
        identifiers=container.identifiers,
        distance_threshold=0.85,
        top_k=5,
        retention_days=1,
    )

    observation = AnswerEvaluator(
        answer_question=answer_question,
        knowledge=knowledge,
        generation=generation,
        distance_threshold=0.85,
    ).run_case(_first_case())

    assert observation.actual_status is None
    assert observation.failure_code == "INVALID_MODEL_OUTPUT"
    assert observation.answer is None
    assert observation.generation_call_count == 1
    assert discard.discarded_count == 0
