"""Capability-separated dependency composition for CLI commands."""

from dataclasses import dataclass
from datetime import UTC, datetime

from google import genai
from google.cloud import firestore_v1

from folioaware.adapters.google import (
    FirestoreKnowledgeRepository,
    FirestoreSyncHistoryRepository,
    VertexEmbeddingProvider,
    create_firestore_client,
    create_vertex_client,
)
from folioaware.adapters.local import (
    DeterministicEmbeddingProvider,
    DeterministicGenerationProvider,
    InMemoryKnowledgeRepository,
    InMemorySyncHistoryRepository,
    SystemClock,
    UUID4Provider,
)
from folioaware.application.answer_question import AnswerQuestion
from folioaware.application.sync_knowledge import SyncKnowledge
from folioaware.config import SyncSettings
from folioaware.domain.knowledge import ApprovedSource
from folioaware.evaluation.answer import (
    AnswerEvaluator,
    DiscardQuestionRepository,
    RecordingKnowledgeRepository,
)
from folioaware.evaluation.retrieval import RetrievalEvaluator
from folioaware.evaluation.runner import OfflineEvaluationRunner
from folioaware.ports.runtime import Clock, IdentifierProvider
from folioaware.security import TelemetrySanitizer


@dataclass(frozen=True, slots=True)
class SyncCommandContainer:
    sync_knowledge: SyncKnowledge


@dataclass(frozen=True, slots=True)
class EvaluationCommandContainer:
    runner: OfflineEvaluationRunner
    discard_questions: DiscardQuestionRepository


class _EvaluationClock:
    def now(self) -> datetime:
        return datetime(2000, 1, 1, tzinfo=UTC)


class _EvaluationIdentifiers:
    def __init__(self) -> None:
        self._next_value = 1

    def new(self) -> str:
        value = f"evaluation-{self._next_value:04d}"
        self._next_value += 1
        return value


def build_evaluation_container(
    sources: tuple[ApprovedSource, ...],
    git_commit: str,
    distance_threshold: float,
    top_k: int,
) -> EvaluationCommandContainer:
    """Compose the credential-free evaluator with discard-only telemetry."""
    clock = _EvaluationClock()
    identifiers = _EvaluationIdentifiers()
    embeddings = DeterministicEmbeddingProvider()
    generation = DeterministicGenerationProvider()
    knowledge = InMemoryKnowledgeRepository()
    discard_questions = DiscardQuestionRepository()
    SyncKnowledge(
        embeddings=embeddings,
        repository=knowledge,
        history=InMemorySyncHistoryRepository(),
        clock=clock,
        identifiers=identifiers,
    ).execute(sources=sources, git_commit=git_commit)
    recording_knowledge = RecordingKnowledgeRepository(knowledge)
    answer_question = AnswerQuestion(
        embeddings=embeddings,
        generation=generation,
        knowledge=recording_knowledge,
        questions=discard_questions,
        sanitizer=TelemetrySanitizer("offline-evaluation-only"),
        clock=clock,
        identifiers=identifiers,
        distance_threshold=distance_threshold,
        top_k=top_k,
        retention_days=1,
    )
    runner = OfflineEvaluationRunner(
        retrieval=RetrievalEvaluator(
            embeddings=embeddings,
            knowledge=recording_knowledge,
            distance_threshold=distance_threshold,
            top_k=top_k,
        ),
        answer=AnswerEvaluator(
            answer_question=answer_question,
            knowledge=recording_knowledge,
            generation=generation,
            distance_threshold=distance_threshold,
        ),
        embeddings=embeddings,
        discard_questions=discard_questions,
        sources=sources,
        content_git_revision=git_commit,
        generator_id=generation.identifier,
    )
    return EvaluationCommandContainer(
        runner=runner,
        discard_questions=discard_questions,
    )


def build_sync_container(
    settings: SyncSettings,
    *,
    vertex_client: genai.Client | None = None,
    firestore_client: firestore_v1.Client | None = None,
    clock: Clock | None = None,
    identifiers: IdentifierProvider | None = None,
) -> SyncCommandContainer:
    """Compose only dependencies that can participate in knowledge sync."""
    resolved_clock = clock or SystemClock()
    resolved_identifiers = identifiers or UUID4Provider()
    if settings.backend == "local":
        sync = SyncKnowledge(
            embeddings=DeterministicEmbeddingProvider(),
            repository=InMemoryKnowledgeRepository(),
            history=InMemorySyncHistoryRepository(),
            clock=resolved_clock,
            identifiers=resolved_identifiers,
        )
        return SyncCommandContainer(sync_knowledge=sync)

    if settings.google_cloud_project is None:
        raise ValueError("validated Google sync configuration is incomplete")
    resolved_vertex = vertex_client or create_vertex_client(
        project=settings.google_cloud_project,
        location=settings.google_cloud_location,
        timeout_seconds=settings.google_request_timeout_seconds,
    )
    resolved_firestore = firestore_client or create_firestore_client(
        project=settings.google_cloud_project,
        database=settings.firestore_database,
    )
    sync = SyncKnowledge(
        embeddings=VertexEmbeddingProvider(
            client=resolved_vertex,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            minimum_interval_seconds=settings.embedding_min_interval_seconds,
        ),
        repository=FirestoreKnowledgeRepository(
            client=resolved_firestore,
            timeout_seconds=settings.google_request_timeout_seconds,
        ),
        history=FirestoreSyncHistoryRepository(
            client=resolved_firestore,
            timeout_seconds=settings.google_request_timeout_seconds,
        ),
        clock=resolved_clock,
        identifiers=resolved_identifiers,
    )
    return SyncCommandContainer(sync_knowledge=sync)
