"""Deterministic extractive generator for local orchestration tests."""

from folioaware.domain.answers import AnswerCandidate, GenerationRequest


class DeterministicGenerationProvider:
    """Return supplied evidence without inventing additional claims."""

    def __init__(self) -> None:
        self.calls = 0

    @property
    def identifier(self) -> str:
        return "local-extractive-v1"

    def generate(self, request: GenerationRequest) -> AnswerCandidate:
        self.calls += 1
        primary = request.evidence[0]
        return AnswerCandidate(
            answer=primary.content,
            evidence_ids=(primary.evidence_id,),
        )
