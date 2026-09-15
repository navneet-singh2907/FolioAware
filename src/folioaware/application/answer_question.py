"""Evidence-gated answer orchestration."""

import logging
from datetime import timedelta

from folioaware.domain.answers import (
    AnswerStatus,
    AskResult,
    Citation,
    Evidence,
    GenerationEvidence,
    GenerationRequest,
)
from folioaware.domain.exceptions import InvalidModelOutputError
from folioaware.domain.knowledge import EmbeddingTaskType
from folioaware.domain.telemetry import VisitorQuestion
from folioaware.ports.embeddings import EmbeddingProvider
from folioaware.ports.generation import GenerationProvider
from folioaware.ports.knowledge_repository import KnowledgeReadRepository
from folioaware.ports.question_repository import QuestionRepository
from folioaware.ports.runtime import Clock, IdentifierProvider
from folioaware.security.telemetry import TelemetrySanitizer

LOGGER = logging.getLogger(__name__)
KNOWLEDGE_GAP_ANSWER = "I don't have verified information about that."
_PREVIOUS_QUESTION_PREFIX = "Previous question: "
_FOLLOW_UP_QUESTION_PREFIX = " Follow-up question: "


class AnswerQuestion:
    def __init__(
        self,
        *,
        embeddings: EmbeddingProvider,
        generation: GenerationProvider,
        knowledge: KnowledgeReadRepository,
        questions: QuestionRepository,
        sanitizer: TelemetrySanitizer,
        clock: Clock,
        identifiers: IdentifierProvider,
        distance_threshold: float,
        top_k: int,
        retention_days: int,
    ) -> None:
        self._embeddings = embeddings
        self._generation = generation
        self._knowledge = knowledge
        self._questions = questions
        self._sanitizer = sanitizer
        self._clock = clock
        self._identifiers = identifiers
        self._distance_threshold = distance_threshold
        self._top_k = top_k
        self._retention_days = retention_days

    def execute(
        self,
        *,
        question: str,
        previous_question: str | None = None,
        session_id: str | None,
    ) -> AskResult:
        normalized_question = " ".join(question.split())
        contextual_question = self._contextual_question(
            normalized_question, previous_question
        )
        request_id = self._identifiers.new()
        version = self._knowledge.get_active_version()
        query_embedding = self._embeddings.embed_query(contextual_question)
        if (
            query_embedding.task_type is not EmbeddingTaskType.RETRIEVAL_QUERY
            or query_embedding.model != version.embedding_model
            or query_embedding.dimensions != version.embedding_dimensions
        ):
            raise InvalidModelOutputError("query embedding is incompatible")

        retrieved = self._knowledge.search(
            query_vector=query_embedding.values,
            index_version=version.index_version,
            limit=self._top_k,
        )
        eligible = tuple(
            evidence
            for evidence in retrieved
            if evidence.distance <= self._distance_threshold
        )
        if not eligible:
            result = AskResult(
                request_id=request_id,
                answer=KNOWLEDGE_GAP_ANSWER,
                answer_status=AnswerStatus.KNOWLEDGE_GAP,
                citations=(),
                knowledge_version=version.index_version,
            )
        else:
            result = self._generate_answer(
                request_id=request_id,
                question=contextual_question,
                knowledge_version=version.index_version,
                evidence=eligible,
            )

        self._record_question(
            result=result,
            normalized_question=normalized_question,
            session_id=session_id,
        )
        return result

    @staticmethod
    def _contextual_question(question: str, previous_question: str | None) -> str:
        if previous_question is None:
            return question
        normalized_previous = " ".join(previous_question.split())
        maximum_previous_length = (
            500
            - len(question)
            - len(_PREVIOUS_QUESTION_PREFIX)
            - len(_FOLLOW_UP_QUESTION_PREFIX)
        )
        if maximum_previous_length < 3:
            return question
        return (
            f"{_PREVIOUS_QUESTION_PREFIX}{normalized_previous[:maximum_previous_length]}"
            f"{_FOLLOW_UP_QUESTION_PREFIX}{question}"
        )

    def _generate_answer(
        self,
        *,
        request_id: str,
        question: str,
        knowledge_version: str,
        evidence: tuple[Evidence, ...],
    ) -> AskResult:
        request = GenerationRequest(
            question=question,
            knowledge_version=knowledge_version,
            evidence=tuple(
                GenerationEvidence(
                    evidence_id=item.evidence_id,
                    content=item.content,
                )
                for item in evidence
            ),
        )
        candidate = self._generation.generate(request)
        if candidate.answer_status is AnswerStatus.KNOWLEDGE_GAP:
            # A semantic mismatch can remain even after the distance gate.
            # Use trusted abstention text rather than displaying ungrounded prose.
            return AskResult(
                request_id=request_id,
                answer=KNOWLEDGE_GAP_ANSWER,
                answer_status=AnswerStatus.KNOWLEDGE_GAP,
                citations=(),
                knowledge_version=knowledge_version,
            )
        evidence_by_id = {item.evidence_id: item for item in evidence}
        if len(set(candidate.evidence_ids)) != len(candidate.evidence_ids):
            raise InvalidModelOutputError("candidate contains duplicate evidence IDs")
        if any(
            evidence_id not in evidence_by_id for evidence_id in candidate.evidence_ids
        ):
            raise InvalidModelOutputError("candidate references unknown evidence")
        # Evidence membership is deterministic; semantic faithfulness of a
        # paraphrase is not. The generation prompt and separate quality evals
        # cover that distinction without pretending substring equality proves it.

        citations_by_source: dict[str, Citation] = {}
        for evidence_id in candidate.evidence_ids:
            item = evidence_by_id[evidence_id]
            citations_by_source.setdefault(
                item.source_id,
                Citation(
                    source_id=item.source_id,
                    title=item.citation_title,
                    url=item.citation_url,
                ),
            )
        if not citations_by_source:
            raise InvalidModelOutputError("substantive answer requires a citation")

        return AskResult(
            request_id=request_id,
            answer=candidate.answer,
            answer_status=AnswerStatus.ANSWERED,
            citations=tuple(citations_by_source.values()),
            knowledge_version=knowledge_version,
        )

    def _record_question(
        self,
        *,
        result: AskResult,
        normalized_question: str,
        session_id: str | None,
    ) -> None:
        now = self._clock.now()
        record = VisitorQuestion(
            question_id=result.request_id,
            redacted_question=self._sanitizer.redact(normalized_question),
            session_hash=self._sanitizer.session_hash(session_id),
            answer_status=result.answer_status,
            knowledge_version=result.knowledge_version,
            created_at=now,
            expires_at=now + timedelta(days=self._retention_days),
        )
        try:
            self._questions.save(record)
        except Exception:
            LOGGER.warning(
                "telemetry_write_failed",
                extra={"request_id": result.request_id},
                exc_info=False,
            )
