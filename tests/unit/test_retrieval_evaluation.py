from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from folioaware.adapters.local import DeterministicEmbeddingProvider
from folioaware.api.dependencies import build_local_container
from folioaware.domain.answers import Evidence
from folioaware.domain.exceptions import InvalidModelOutputError
from folioaware.domain.knowledge import (
    Embedding,
    EmbeddingTaskType,
    IndexStatus,
    IndexVersion,
)
from folioaware.evaluation import (
    ContextRelevanceMetric,
    EvaluationCase,
    EvaluationStatus,
    EvaluationSuite,
    EvaluationTag,
    RankedRetrievalCandidate,
    RatioMetric,
    RelevantPassage,
    RetrievalCaseResult,
    RetrievalEvaluator,
    candidate_is_relevant,
    load_evaluation_suite,
    summarize_retrieval_cases,
)
from folioaware.ingestion import load_approved_sources


def _case(
    case_id: str,
    *,
    answered: bool = True,
    passage: str = "The approved supporting passage.",
) -> EvaluationCase:
    return EvaluationCase(
        case_id=case_id,
        question=f"Question for {case_id}?",
        expected_status=(
            EvaluationStatus.ANSWERED if answered else EvaluationStatus.KNOWLEDGE_GAP
        ),
        reference_answer="Supported answer." if answered else None,
        relevant_passages=(
            (RelevantPassage(source_id="source-a", text=passage),) if answered else ()
        ),
        required_citation_source_ids=("source-a",) if answered else (),
        tags=(
            (EvaluationTag.ANSWERABLE,) if answered else (EvaluationTag.UNANSWERABLE,)
        ),
    )


def _evidence(
    evidence_id: str,
    *,
    source_id: str = "source-a",
    content: str = "The approved supporting passage.",
    distance: float = 0.2,
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_id=source_id,
        content=content,
        citation_title="Synthetic source",
        citation_url="/synthetic",
        index_version="version-1",
        distance=distance,
    )


class FixedKnowledgeRepository:
    def __init__(self, results: dict[str, tuple[Evidence, ...]]) -> None:
        self.results = results
        self.queries: list[tuple[tuple[float, ...], str, int]] = []

    def get_active_version(self) -> IndexVersion:
        return IndexVersion(
            index_version="version-1",
            git_commit="0000000",
            status=IndexStatus.ACTIVE,
            source_count=2,
            chunk_count=2,
            embedding_model="query-key-v1",
            embedding_dimensions=8,
            created_at=datetime(2026, 9, 3, tzinfo=UTC),
            activated_at=datetime(2026, 9, 3, tzinfo=UTC),
        )

    def search(
        self,
        *,
        query_vector: tuple[float, ...],
        index_version: str,
        limit: int,
    ) -> tuple[Evidence, ...]:
        self.queries.append((query_vector, index_version, limit))
        key = str(round(query_vector[0]))
        return self.results.get(key, ())


class QueryKeyEmbeddings:
    model = "query-key-v1"
    dimensions = 8

    def embed_document(self, _text: str) -> Embedding:
        raise AssertionError("retrieval evaluation must not embed documents")

    def embed_query(self, text: str) -> Embedding:
        key = float(text.split("case-")[-1].rstrip("?"))
        return Embedding(
            values=(key, 0, 0, 0, 0, 0, 0, 0),
            model=self.model,
            task_type=EmbeddingTaskType.RETRIEVAL_QUERY,
            dimensions=self.dimensions,
        )


def _suite(*cases: EvaluationCase) -> EvaluationSuite:
    return EvaluationSuite(
        schema_version=1,
        suite_id="test-suite",
        description="Synthetic retrieval metric tests.",
        policy_version="evidence-policy-v1",
        cases=cases,
    )


def test_relevance_requires_matching_source_and_normalized_passage() -> None:
    case = _case("case-1")

    assert candidate_is_relevant(
        _evidence(
            "relevant",
            content="Prefix.  The approved\n supporting passage. Suffix.",
        ),
        case,
    )
    assert not candidate_is_relevant(
        _evidence("wrong-source", source_id="source-b"), case
    )
    assert not candidate_is_relevant(
        _evidence("wrong-passage", content="A plausible but unannotated passage."),
        case,
    )


def test_runner_records_pre_threshold_candidates_and_mixed_metrics() -> None:
    cases = (_case("case-1"), _case("case-2"), _case("case-3", answered=False))
    repository = FixedKnowledgeRepository(
        {
            "1": (
                _evidence("relevant-but-rejected", distance=0.9),
                _evidence(
                    "distractor",
                    source_id="source-b",
                    content="Unrelated content.",
                    distance=0.1,
                ),
            ),
            "2": (),
            "3": (_evidence("unanswerable-distractor", distance=0.2),),
        }
    )

    result = RetrievalEvaluator(
        embeddings=QueryKeyEmbeddings(),
        knowledge=repository,
        distance_threshold=0.85,
        top_k=2,
    ).run(_suite(*cases))

    first = result.cases[0]
    assert [candidate.rank for candidate in first.candidates] == [1, 2]
    assert first.candidates[0].relevant is True
    assert first.candidates[0].threshold_eligible is False
    assert first.hit is True
    assert first.context_relevance == Decimal("0.5")
    assert result.cases[1].candidates == ()
    assert result.cases[1].hit is False
    assert result.hit_at_k.model_dump() == {
        "numerator": 1,
        "denominator": 2,
        "value": Decimal("0.5"),
    }
    assert result.context_relevance_at_k.relevant_candidates == 1
    assert result.context_relevance_at_k.returned_candidates == 2
    assert result.context_relevance_at_k.case_count == 2
    assert result.context_relevance_at_k.value == Decimal("0.25")
    assert len(repository.queries) == 3


@pytest.mark.parametrize(
    ("case_results", "hit_value", "context_value"),
    [
        ((), Decimal(0), Decimal(0)),
        (
            (
                RetrievalCaseResult(
                    case_id="perfect",
                    expected_status=EvaluationStatus.ANSWERED,
                    candidates=(
                        RankedRetrievalCandidate(
                            evidence_id="perfect-evidence",
                            source_id="source-a",
                            rank=1,
                            distance=0.1,
                            threshold_eligible=True,
                            relevant=True,
                        ),
                    ),
                    hit=True,
                    relevant_candidate_count=1,
                    returned_candidate_count=1,
                    context_relevance=Decimal(1),
                ),
            ),
            Decimal(1),
            Decimal(1),
        ),
        (
            (
                RetrievalCaseResult(
                    case_id="empty",
                    expected_status=EvaluationStatus.ANSWERED,
                    candidates=(),
                    hit=False,
                    relevant_candidate_count=0,
                    returned_candidate_count=0,
                    context_relevance=Decimal(0),
                ),
            ),
            Decimal(0),
            Decimal(0),
        ),
    ],
)
def test_metric_boundaries(
    case_results: tuple[RetrievalCaseResult, ...],
    hit_value: Decimal,
    context_value: Decimal,
) -> None:
    hit, context = summarize_retrieval_cases(case_results)

    assert hit.value == hit_value
    assert context.value == context_value


def test_rejects_diagnostics_that_disagree_with_candidates() -> None:
    candidate = RankedRetrievalCandidate(
        evidence_id="evidence-1",
        source_id="source-a",
        rank=1,
        distance=0.2,
        threshold_eligible=True,
        relevant=True,
    )

    with pytest.raises(ValidationError, match="relevant candidate count"):
        RetrievalCaseResult(
            case_id="inconsistent",
            expected_status=EvaluationStatus.ANSWERED,
            candidates=(candidate,),
            hit=True,
            relevant_candidate_count=0,
            returned_candidate_count=1,
            context_relevance=Decimal(1),
        )


@pytest.mark.parametrize(
    ("metric", "message"),
    [
        (
            lambda: RatioMetric(numerator=2, denominator=1, value=Decimal(1)),
            "numerator cannot exceed",
        ),
        (
            lambda: RatioMetric(numerator=1, denominator=2, value=Decimal("0.4")),
            "value must match",
        ),
        (
            lambda: ContextRelevanceMetric(
                relevant_candidates=2,
                returned_candidates=1,
                case_count=1,
                value=Decimal(1),
            ),
            "cannot exceed",
        ),
        (
            lambda: ContextRelevanceMetric(
                relevant_candidates=0,
                returned_candidates=0,
                case_count=0,
                value=Decimal("0.5"),
            ),
            "must be zero",
        ),
    ],
)
def test_rejects_invalid_metric_contracts(
    metric: Callable[[], object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        metric()


def test_runs_complete_synthetic_suite_without_answer_generation() -> None:
    content_root = Path("examples/synthetic-portfolio")
    sources = load_approved_sources(content_root)
    suite = load_evaluation_suite(
        Path("evals/fixtures/synthetic-portfolio-v1.yaml"),
        approved_sources=sources,
    )
    container = build_local_container(content_root=content_root)
    query_calls_before = container.embeddings.query_calls

    result = RetrievalEvaluator(
        embeddings=container.embeddings,
        knowledge=container.knowledge,
        distance_threshold=0.85,
        top_k=5,
    ).run(suite)

    assert len(result.cases) == 24
    assert result.hit_at_k.denominator == 12
    assert result.context_relevance_at_k.case_count == 12
    assert container.embeddings.query_calls == query_calls_before + 24
    assert container.generation.calls == 0
    assert all(len(case.candidates) <= 5 for case in result.cases)


def test_runner_rejects_incompatible_query_embedding() -> None:
    class IncompatibleEmbeddings(DeterministicEmbeddingProvider):
        @property
        def model(self) -> str:
            return "wrong-model"

    with pytest.raises(InvalidModelOutputError, match="incompatible"):
        RetrievalEvaluator(
            embeddings=IncompatibleEmbeddings(dimensions=8),
            knowledge=FixedKnowledgeRepository({}),
            distance_threshold=0.85,
            top_k=2,
        ).run(_suite(_case("case-1")))


@pytest.mark.parametrize(
    ("threshold", "top_k", "message"),
    [
        (0.85, 0, "top_k"),
        (float("nan"), 1, "distance_threshold"),
        (2.1, 1, "distance_threshold"),
    ],
)
def test_runner_rejects_invalid_configuration(
    threshold: float, top_k: int, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        RetrievalEvaluator(
            embeddings=QueryKeyEmbeddings(),
            knowledge=FixedKnowledgeRepository({}),
            distance_threshold=threshold,
            top_k=top_k,
        )
