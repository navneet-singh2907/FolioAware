"""Local dependency composition for the first vertical slice."""

from dataclasses import dataclass
from pathlib import Path

from google import genai
from google.cloud import firestore_v1
from pydantic import SecretStr

from folioaware.adapters.google import (
    FirestoreInsightRepository,
    FirestoreKnowledgeRepository,
    FirestoreQuestionRepository,
    VertexEmbeddingProvider,
    VertexGenerationProvider,
    create_firestore_client,
    create_vertex_client,
)
from folioaware.adapters.local import (
    DeterministicEmbeddingProvider,
    DeterministicGenerationProvider,
    InMemoryInsightRepository,
    InMemoryKnowledgeRepository,
    InMemoryQuestionRepository,
    SystemClock,
    UUID4Provider,
)
from folioaware.analytics import DeterministicQuestionClassifier, load_topic_rules
from folioaware.application.answer_question import AnswerQuestion
from folioaware.application.generate_insights import GenerateInsightReport
from folioaware.application.sync_knowledge import SyncKnowledge
from folioaware.config import Settings
from folioaware.ingestion import load_approved_sources
from folioaware.ports.runtime import Clock, IdentifierProvider
from folioaware.security import TelemetrySanitizer


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    answer_question: AnswerQuestion
    generate_insights: GenerateInsightReport
    clock: Clock
    identifiers: IdentifierProvider
    owner_report_token: SecretStr


@dataclass(frozen=True, slots=True)
class LocalApplicationContainer(ApplicationContainer):
    knowledge: InMemoryKnowledgeRepository
    questions: InMemoryQuestionRepository
    insights: InMemoryInsightRepository
    embeddings: DeterministicEmbeddingProvider
    generation: DeterministicGenerationProvider


@dataclass(frozen=True, slots=True)
class GoogleApplicationContainer(ApplicationContainer):
    knowledge: FirestoreKnowledgeRepository
    questions: FirestoreQuestionRepository
    insights: FirestoreInsightRepository
    embeddings: VertexEmbeddingProvider
    generation: VertexGenerationProvider


def build_local_container(
    settings: Settings | None = None,
    *,
    content_root: Path | None = None,
) -> LocalApplicationContainer:
    resolved_settings = settings or Settings()
    clock = SystemClock()
    identifiers = UUID4Provider()
    embeddings = DeterministicEmbeddingProvider()
    generation = DeterministicGenerationProvider()
    knowledge = InMemoryKnowledgeRepository()
    questions = InMemoryQuestionRepository()
    insights = InMemoryInsightRepository()
    classifier = DeterministicQuestionClassifier(
        load_topic_rules(resolved_settings.insight_rules_path)
    )
    sources = load_approved_sources(content_root or resolved_settings.content_root)
    SyncKnowledge(
        embeddings=embeddings,
        repository=knowledge,
        clock=clock,
        identifiers=identifiers,
    ).execute(sources=sources, git_commit="0000000")
    answer_question = AnswerQuestion(
        embeddings=embeddings,
        generation=generation,
        knowledge=knowledge,
        questions=questions,
        sanitizer=TelemetrySanitizer(
            resolved_settings.session_hash_secret.get_secret_value()
        ),
        clock=clock,
        identifiers=identifiers,
        distance_threshold=resolved_settings.retrieval_distance_threshold,
        top_k=resolved_settings.retrieval_top_k,
        retention_days=resolved_settings.telemetry_retention_days,
    )
    return LocalApplicationContainer(
        answer_question=answer_question,
        generate_insights=GenerateInsightReport(
            questions=questions,
            classifier=classifier,
            insights=insights,
            clock=clock,
            minimum_question_count=resolved_settings.insight_min_question_count,
        ),
        clock=clock,
        identifiers=identifiers,
        owner_report_token=resolved_settings.owner_report_token,
        knowledge=knowledge,
        questions=questions,
        insights=insights,
        embeddings=embeddings,
        generation=generation,
    )


def build_google_container(
    settings: Settings,
    *,
    vertex_client: genai.Client | None = None,
    firestore_client: firestore_v1.Client | None = None,
) -> GoogleApplicationContainer:
    """Compose Google adapters; client injection keeps tests credential-free."""
    if settings.backend != "google":
        raise ValueError("Google composition requires backend=google")
    if settings.google_cloud_project is None or settings.generation_model is None:
        raise ValueError("validated Google configuration is incomplete")

    resolved_vertex = vertex_client or create_vertex_client(
        project=settings.google_cloud_project,
        location=settings.google_cloud_location,
        timeout_seconds=settings.google_request_timeout_seconds,
    )
    resolved_firestore = firestore_client or create_firestore_client(
        project=settings.google_cloud_project,
        database=settings.firestore_database,
    )
    clock = SystemClock()
    identifiers = UUID4Provider()
    embeddings = VertexEmbeddingProvider(
        client=resolved_vertex,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    generation = VertexGenerationProvider(
        client=resolved_vertex,
        model=settings.generation_model,
        max_output_tokens=settings.generation_max_output_tokens,
    )
    knowledge = FirestoreKnowledgeRepository(
        client=resolved_firestore,
        timeout_seconds=settings.google_request_timeout_seconds,
    )
    questions = FirestoreQuestionRepository(
        client=resolved_firestore,
        timeout_seconds=settings.google_request_timeout_seconds,
    )
    insights = FirestoreInsightRepository(
        client=resolved_firestore,
        timeout_seconds=settings.google_request_timeout_seconds,
    )
    classifier = DeterministicQuestionClassifier(
        load_topic_rules(settings.insight_rules_path)
    )
    answer_question = AnswerQuestion(
        embeddings=embeddings,
        generation=generation,
        knowledge=knowledge,
        questions=questions,
        sanitizer=TelemetrySanitizer(settings.session_hash_secret.get_secret_value()),
        clock=clock,
        identifiers=identifiers,
        distance_threshold=settings.retrieval_distance_threshold,
        top_k=settings.retrieval_top_k,
        retention_days=settings.telemetry_retention_days,
    )
    return GoogleApplicationContainer(
        answer_question=answer_question,
        generate_insights=GenerateInsightReport(
            questions=questions,
            classifier=classifier,
            insights=insights,
            clock=clock,
            minimum_question_count=settings.insight_min_question_count,
        ),
        clock=clock,
        identifiers=identifiers,
        owner_report_token=settings.owner_report_token,
        knowledge=knowledge,
        questions=questions,
        insights=insights,
        embeddings=embeddings,
        generation=generation,
    )


def build_container(settings: Settings | None = None) -> ApplicationContainer:
    resolved = settings or Settings()
    if resolved.backend == "google":
        return build_google_container(resolved)
    return build_local_container(resolved)
