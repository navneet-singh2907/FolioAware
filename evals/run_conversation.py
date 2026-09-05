"""Opt-in, bounded Vertex generation evaluation; never run by default in CI.

Prints synthetic inputs, generated answers, timings, and review criteria. It
does not score semantic faithfulness automatically or write visitor telemetry.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

from folioaware.adapters.google.vertex import (
    SYSTEM_INSTRUCTION,
    VertexGenerationProvider,
    create_vertex_client,
)
from folioaware.domain.answers import GenerationEvidence, GenerationRequest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-live", action="store_true", help="Allow paid Vertex calls"
    )
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    if not args.run_live:
        parser.error("--run-live is required; this evaluation calls Vertex AI")
    raw_suite = (Path(__file__).parent / "fixtures/conversation-v1.json").read_bytes()
    suite = json.loads(raw_suite)
    client = create_vertex_client(
        project=args.project, location="global", timeout_seconds=15
    )
    provider = VertexGenerationProvider(
        client=client, model="gemini-2.5-flash", max_output_tokens=1024
    )
    print(
        json.dumps(
            {
                "suite": suite["suite"],
                "model": "gemini-2.5-flash",
                "location": "global",
                "temperature": 0.3,
                "thinkingBudget": 256,
                "maxOutputTokens": 1024,
                "promptSha256": hashlib.sha256(SYSTEM_INSTRUCTION.encode()).hexdigest(),
                "suiteSha256": hashlib.sha256(raw_suite).hexdigest(),
                "semanticReview": "Required; structure checks do not prove entailment",
            }
        ),
        flush=True,
    )
    try:
        for case in suite["cases"]:
            evidence = list(suite["evidence"])
            if "extraEvidence" in case:
                evidence.append(case["extraEvidence"])
            request = GenerationRequest(
                question=case["question"],
                knowledge_version=suite["suite"],
                evidence=tuple(
                    GenerationEvidence.model_validate(item) for item in evidence
                ),
            )
            start = time.monotonic()
            candidate = provider.generate(request)
            assert set(candidate.evidence_ids) <= {
                item.evidence_id for item in request.evidence
            }
            assert len(candidate.evidence_ids) == len(set(candidate.evidence_ids))
            if case["status"] != "answered_or_gap":
                assert candidate.answer_status == case["status"], case["id"]
            print(
                json.dumps(
                    {
                        "id": case["id"],
                        "question": case["question"],
                        "candidate": candidate.model_dump(mode="json", by_alias=True),
                        "seconds": round(time.monotonic() - start, 2),
                        "review": case["review"],
                    }
                ),
                flush=True,
            )
    finally:
        client.close()


if __name__ == "__main__":
    main()
