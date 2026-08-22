"""Local dependency composition for the first vertical slice."""

from dataclasses import dataclass
from pathlib import Path

from folioaware.adapters.local import (
    DeterministicEmbeddingProvider,
    DeterministicGenerationProvider,
    InMemoryKnowledgeRepository,
    InMemoryQuestionRepository,
    SystemClock,
    UUID4Provider,
)
from folioaware.application.answer_question import AnswerQuestion
from folioaware.application.sync_knowledge import SyncKnowledge
from folioaware.config import Settings
from folioaware.ingestion import load_approved_sources
from folioaware.ports.runtime import Clock, IdentifierProvider
from folioaware.security import TelemetrySanitizer


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    answer_question: AnswerQuestion
    clock: Clock
    identifiers: IdentifierProvider
    knowledge: InMemoryKnowledgeRepository
    questions: InMemoryQuestionRepository
    embeddings: DeterministicEmbeddingProvider
    generation: DeterministicGenerationProvider


def build_local_container(
    settings: Settings | None = None,
    *,
    content_root: Path | None = None,
) -> ApplicationContainer:
    resolved_settings = settings or Settings()
    clock = SystemClock()
    identifiers = UUID4Provider()
    embeddings = DeterministicEmbeddingProvider()
    generation = DeterministicGenerationProvider()
    knowledge = InMemoryKnowledgeRepository()
    questions = InMemoryQuestionRepository()
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
    return ApplicationContainer(
        answer_question=answer_question,
        clock=clock,
        identifiers=identifiers,
        knowledge=knowledge,
        questions=questions,
        embeddings=embeddings,
        generation=generation,
    )
