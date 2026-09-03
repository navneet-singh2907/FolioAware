"""Two-plane orchestration for deterministic offline evaluation."""

from __future__ import annotations

from collections.abc import Sequence

from folioaware.domain.knowledge import ApprovedSource
from folioaware.evaluation.answer import (
    AnswerEvaluator,
    AnswerObservation,
    DiscardQuestionRepository,
)
from folioaware.evaluation.models import EvaluationSuite
from folioaware.evaluation.report import EvaluationReport, build_report
from folioaware.evaluation.retrieval import RetrievalEvaluator
from folioaware.ports.embeddings import EmbeddingProvider


class OfflineEvaluationRunner:
    """Run retrieval and answer planes against one isolated local index."""

    def __init__(
        self,
        *,
        retrieval: RetrievalEvaluator,
        answer: AnswerEvaluator,
        embeddings: EmbeddingProvider,
        discard_questions: DiscardQuestionRepository,
        sources: Sequence[ApprovedSource],
        content_git_revision: str,
        generator_id: str,
    ) -> None:
        self._retrieval = retrieval
        self._answer = answer
        self._embeddings = embeddings
        self._discard_questions = discard_questions
        self._sources = tuple(sources)
        self._content_git_revision = content_git_revision
        self._generator_id = generator_id

    def run(self, suite: EvaluationSuite) -> EvaluationReport:
        retrieval_result = self._retrieval.run(suite)
        observations: list[AnswerObservation] = []
        for case in suite.cases:
            observations.append(self._answer.run_case(case))
        return build_report(
            suite=suite,
            sources=self._sources,
            retrieval=retrieval_result,
            observations=observations,
            content_git_revision=self._content_git_revision,
            embedding_model=self._embeddings.model,
            embedding_dimensions=self._embeddings.dimensions,
            generator_id=self._generator_id,
            discarded_question_count=self._discard_questions.discarded_count,
        )
