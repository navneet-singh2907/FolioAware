"""Answer-plane evaluation through the production evidence-gated use case."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from folioaware.application.answer_question import AnswerQuestion
from folioaware.domain.answers import AnswerStatus, Evidence
from folioaware.domain.exceptions import InvalidModelOutputError
from folioaware.domain.knowledge import IndexVersion
from folioaware.domain.telemetry import VisitorQuestion
from folioaware.evaluation.models import EvaluationCase, normalize_evaluation_text
from folioaware.ports.knowledge_repository import KnowledgeReadRepository


class GenerationCallObserver(Protocol):
    @property
    def calls(self) -> int: ...


class DiscardQuestionRepository:
    """Accept evaluation telemetry writes without retaining visitor records."""

    def __init__(self) -> None:
        self.discarded_count = 0

    def save(self, _question: VisitorQuestion) -> None:
        self.discarded_count += 1


class RecordingKnowledgeRepository:
    """Observe the exact evidence returned to the normal answer use case."""

    def __init__(self, delegate: KnowledgeReadRepository) -> None:
        self._delegate = delegate
        self.last_search: tuple[Evidence, ...] = ()

    def reset(self) -> None:
        self.last_search = ()

    def get_active_version(self) -> IndexVersion:
        return self._delegate.get_active_version()

    def search(
        self,
        *,
        query_vector: tuple[float, ...],
        index_version: str,
        limit: int,
    ) -> Sequence[Evidence]:
        self.last_search = tuple(
            self._delegate.search(
                query_vector=query_vector,
                index_version=index_version,
                limit=limit,
            )
        )
        return self.last_search


@dataclass(frozen=True, slots=True)
class AnswerObservation:
    """Internal answer result containing only data required for scoring."""

    actual_status: AnswerStatus | None
    citation_source_ids: tuple[str, ...]
    generation_call_count: int
    failure_code: str | None
    eligible_evidence: tuple[Evidence, ...]
    answer: str | None


class AnswerEvaluator:
    """Run each case through AnswerQuestion and observe bounded diagnostics."""

    def __init__(
        self,
        *,
        answer_question: AnswerQuestion,
        knowledge: RecordingKnowledgeRepository,
        generation: GenerationCallObserver,
        distance_threshold: float,
    ) -> None:
        self._answer_question = answer_question
        self._knowledge = knowledge
        self._generation = generation
        self._distance_threshold = distance_threshold

    def run_case(self, case: EvaluationCase) -> AnswerObservation:
        self._knowledge.reset()
        calls_before = self._generation.calls
        try:
            result = self._answer_question.execute(
                question=case.question,
                session_id=None,
            )
        except InvalidModelOutputError:
            return AnswerObservation(
                actual_status=None,
                citation_source_ids=(),
                generation_call_count=self._generation.calls - calls_before,
                failure_code="INVALID_MODEL_OUTPUT",
                eligible_evidence=self._eligible_evidence(),
                answer=None,
            )

        return AnswerObservation(
            actual_status=result.answer_status,
            citation_source_ids=tuple(
                citation.source_id for citation in result.citations
            ),
            generation_call_count=self._generation.calls - calls_before,
            failure_code=None,
            eligible_evidence=self._eligible_evidence(),
            answer=normalize_evaluation_text(result.answer),
        )

    def _eligible_evidence(self) -> tuple[Evidence, ...]:
        return tuple(
            evidence
            for evidence in self._knowledge.last_search
            if evidence.distance <= self._distance_threshold
        )
