"""Deterministic retrieval-plane evaluation and diagnostics."""

from __future__ import annotations

import math
from decimal import Decimal
from fractions import Fraction

from pydantic import Field, field_validator, model_validator

from folioaware.domain.answers import Evidence
from folioaware.domain.base import DomainModel
from folioaware.domain.exceptions import InvalidModelOutputError
from folioaware.domain.knowledge import EmbeddingTaskType
from folioaware.evaluation.models import (
    EvaluationCase,
    EvaluationStatus,
    EvaluationSuite,
    normalize_evaluation_text,
)
from folioaware.ports.embeddings import EmbeddingProvider
from folioaware.ports.knowledge_repository import KnowledgeReadRepository


class RatioMetric(DomainModel):
    """One exact count ratio with a deterministic decimal representation."""

    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    value: Decimal = Field(ge=0, le=1)

    @model_validator(mode="after")
    def value_matches_counts(self) -> RatioMetric:
        if self.numerator > self.denominator:
            raise ValueError("metric numerator cannot exceed denominator")
        if self.value != _decimal_ratio(self.numerator, self.denominator):
            raise ValueError("metric value must match its counts")
        return self


class RankedRetrievalCandidate(DomainModel):
    evidence_id: str = Field(min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=100)
    rank: int = Field(ge=1)
    distance: float = Field(ge=0, le=2)
    threshold_eligible: bool
    relevant: bool

    @field_validator("distance")
    @classmethod
    def distance_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("candidate distance must be finite")
        return value


class RetrievalCaseResult(DomainModel):
    case_id: str = Field(min_length=1, max_length=100)
    expected_status: EvaluationStatus
    candidates: tuple[RankedRetrievalCandidate, ...]
    hit: bool
    relevant_candidate_count: int = Field(ge=0)
    returned_candidate_count: int = Field(ge=0)
    context_relevance: Decimal = Field(ge=0, le=1)

    @model_validator(mode="after")
    def diagnostics_match_candidates(self) -> RetrievalCaseResult:
        expected_ranks = tuple(range(1, len(self.candidates) + 1))
        if tuple(candidate.rank for candidate in self.candidates) != expected_ranks:
            raise ValueError("candidate ranks must be contiguous and one-based")
        relevant_count = sum(candidate.relevant for candidate in self.candidates)
        if self.relevant_candidate_count != relevant_count:
            raise ValueError("relevant candidate count does not match candidates")
        if self.returned_candidate_count != len(self.candidates):
            raise ValueError("returned candidate count does not match candidates")
        if self.hit is not (relevant_count > 0):
            raise ValueError("retrieval hit does not match candidates")
        if self.context_relevance != _decimal_ratio(
            relevant_count, len(self.candidates)
        ):
            raise ValueError("context relevance does not match candidates")
        return self


class ContextRelevanceMetric(DomainModel):
    """Macro mean of per-case relevance ratios plus transparent raw counts."""

    relevant_candidates: int = Field(ge=0)
    returned_candidates: int = Field(ge=0)
    case_count: int = Field(ge=0)
    value: Decimal = Field(ge=0, le=1)

    @model_validator(mode="after")
    def counts_are_consistent(self) -> ContextRelevanceMetric:
        if self.relevant_candidates > self.returned_candidates:
            raise ValueError("relevant candidates cannot exceed returned candidates")
        if self.case_count == 0 and self.value != 0:
            raise ValueError("empty context relevance must be zero")
        return self


class RetrievalEvaluationResult(DomainModel):
    top_k: int = Field(ge=1)
    distance_threshold: float = Field(ge=0, le=2)
    cases: tuple[RetrievalCaseResult, ...]
    hit_at_k: RatioMetric
    context_relevance_at_k: ContextRelevanceMetric

    @model_validator(mode="after")
    def aggregate_matches_cases(self) -> RetrievalEvaluationResult:
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("retrieval case IDs must be unique")
        if any(len(case.candidates) > self.top_k for case in self.cases):
            raise ValueError("retrieval case exceeds top_k")
        expected_hit, expected_context = summarize_retrieval_cases(self.cases)
        if self.hit_at_k != expected_hit:
            raise ValueError("Hit@K does not match retrieval cases")
        if self.context_relevance_at_k != expected_context:
            raise ValueError("Context Relevance@K does not match retrieval cases")
        return self


def _decimal_ratio(numerator: int, denominator: int) -> Decimal:
    if denominator == 0:
        return Decimal(0)
    return Decimal(numerator) / Decimal(denominator)


def candidate_is_relevant(candidate: Evidence, case: EvaluationCase) -> bool:
    """Match an annotated source and passage against normalized candidate text."""
    content = normalize_evaluation_text(candidate.content)
    return any(
        passage.source_id == candidate.source_id and passage.text in content
        for passage in case.relevant_passages
    )


def summarize_retrieval_cases(
    cases: tuple[RetrievalCaseResult, ...],
) -> tuple[RatioMetric, ContextRelevanceMetric]:
    answerable = tuple(
        case for case in cases if case.expected_status is EvaluationStatus.ANSWERED
    )
    hit_count = sum(case.hit for case in answerable)
    hit_at_k = RatioMetric(
        numerator=hit_count,
        denominator=len(answerable),
        value=_decimal_ratio(hit_count, len(answerable)),
    )
    context_fraction = sum(
        (
            Fraction(
                case.relevant_candidate_count,
                case.returned_candidate_count,
            )
            if case.returned_candidate_count
            else Fraction(0)
            for case in answerable
        ),
        start=Fraction(0),
    )
    context_fraction = context_fraction / len(answerable) if answerable else Fraction(0)
    context_value = _decimal_ratio(
        context_fraction.numerator, context_fraction.denominator
    )
    context_relevance = ContextRelevanceMetric(
        relevant_candidates=sum(case.relevant_candidate_count for case in answerable),
        returned_candidates=sum(case.returned_candidate_count for case in answerable),
        case_count=len(answerable),
        value=context_value,
    )
    return hit_at_k, context_relevance


class RetrievalEvaluator:
    """Observe retrieval before the answer policy applies its distance gate."""

    def __init__(
        self,
        *,
        embeddings: EmbeddingProvider,
        knowledge: KnowledgeReadRepository,
        distance_threshold: float,
        top_k: int,
    ) -> None:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        if not math.isfinite(distance_threshold) or not 0 <= distance_threshold <= 2:
            raise ValueError("distance_threshold must be finite and between 0 and 2")
        self._embeddings = embeddings
        self._knowledge = knowledge
        self._distance_threshold = distance_threshold
        self._top_k = top_k

    def run(self, suite: EvaluationSuite) -> RetrievalEvaluationResult:
        version = self._knowledge.get_active_version()
        results: list[RetrievalCaseResult] = []
        for case in suite.cases:
            query_embedding = self._embeddings.embed_query(case.question)
            if (
                query_embedding.task_type is not EmbeddingTaskType.RETRIEVAL_QUERY
                or query_embedding.model != version.embedding_model
                or query_embedding.dimensions != version.embedding_dimensions
            ):
                raise InvalidModelOutputError("query embedding is incompatible")

            evidence = tuple(
                self._knowledge.search(
                    query_vector=query_embedding.values,
                    index_version=version.index_version,
                    limit=self._top_k,
                )
            )[: self._top_k]
            candidates = tuple(
                RankedRetrievalCandidate(
                    evidence_id=item.evidence_id,
                    source_id=item.source_id,
                    rank=rank,
                    distance=item.distance,
                    threshold_eligible=item.distance <= self._distance_threshold,
                    relevant=candidate_is_relevant(item, case),
                )
                for rank, item in enumerate(evidence, start=1)
            )
            relevant_count = sum(candidate.relevant for candidate in candidates)
            returned_count = len(candidates)
            results.append(
                RetrievalCaseResult(
                    case_id=case.case_id,
                    expected_status=case.expected_status,
                    candidates=candidates,
                    hit=relevant_count > 0,
                    relevant_candidate_count=relevant_count,
                    returned_candidate_count=returned_count,
                    context_relevance=_decimal_ratio(relevant_count, returned_count),
                )
            )

        case_results = tuple(results)
        hit_at_k, context_relevance_at_k = summarize_retrieval_cases(case_results)
        return RetrievalEvaluationResult(
            top_k=self._top_k,
            distance_threshold=self._distance_threshold,
            cases=case_results,
            hit_at_k=hit_at_k,
            context_relevance_at_k=context_relevance_at_k,
        )
