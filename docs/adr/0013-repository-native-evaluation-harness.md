# ADR-0013: Repository-native, two-plane evaluation harness

- Status: Accepted
- Date: 2026-09-01

## Context

FolioAware has deterministic synchronization, retrieval, evidence gating, and
answer validation, but it does not yet measure retrieval quality across a
versioned question set. Endpoint tests prove selected behaviors; they do not
show whether ranked context is noisy, whether an answerable paraphrase was
missed, or whether threshold changes increase unsupported answers.

The public API intentionally returns only the final answer and citations. A
retrieval evaluation needs the ranked candidates and distances before the
answer-time threshold is applied. An answer-policy evaluation needs the final
status, citations, and evidence membership after the complete application
workflow. Combining these into one opaque score would hide the failure stage.

## Options considered

### Black-box API evaluation only

Send fixture questions to `POST /v1/ask` and score final responses. This tests
the deployed contract but cannot distinguish retrieval misses from threshold,
generation, or citation failures. It also cannot measure context noise because
ranked candidates are deliberately absent from the public response.

### Repository-native two-plane harness

Build a developer-facing evaluator that uses the same embedding, knowledge,
generation, and evidence contracts as the application. The retrieval plane
records ranked candidates before the distance gate. The answer plane invokes
the normal use case with isolated in-memory telemetry and scores its final
status and citations. This adds project-owned contracts and metric code, but it
keeps every formula inspectable, offline, typed, and deterministic.

### Third-party or model-judged evaluation framework

Add Ragas, DeepEval, an orchestration framework, or an LLM judge. These can
provide semantic faithfulness judgments, but they add dependencies, model
cost, judge variance, prompt/version management, and potential data processing
before FolioAware has a deterministic baseline. They are not needed to measure
known synthetic passages, retrieval ranking, abstention, or citation
membership.

## Decision

Use a repository-native two-plane evaluation harness for the MVP.

```text
versioned synthetic suite
          |
          +--> retrieval plane --> ranked candidates + distances
          |                         --> Hit@K + context relevance
          |
          +--> answer plane ------> answered | knowledge_gap
                                    --> abstention + citation metrics
```

Evaluation is developer tooling, not a public endpoint or production data
pipeline. Its code belongs under `folioaware.evaluation`; versioned public
fixtures and accepted deterministic baselines belong under `evals/`. It may
depend on domain models and ports, while a CLI composition root selects local
or explicitly opted-in provider adapters.

The first implementation is fully offline. It synchronizes the synthetic
portfolio into an in-memory repository and uses the deterministic local
embedding and extractive generation adapters. It writes no visitor telemetry,
calls no Google API, and creates no cloud resource. A provider-backed run must
later be an explicit, non-CI mode with its model, region, prompt, cost, and data
handling recorded in the report.

Ground truth uses stable source IDs plus exact supporting passages, not current
chunk IDs. Chunk IDs contain content hashes and can change when chunking is
intentionally benchmarked. A retrieved chunk is relevant only when it has the
annotated source ID and contains an annotated passage after newline/whitespace
normalization. This prevents any chunk from a broadly related project being
counted as useful context.

The harness reports retrieval and policy metrics separately. It never averages
safety failures into a high overall score. Hard invariants have zero tolerance;
semantic retrieval metrics establish a measured baseline before numerical
release targets are adopted.

## Consequences

- Metric formulas and case-level evidence remain reviewable in this repository.
- Retrieval, threshold, generation, and citation failures are distinguishable.
- CI stays offline, deterministic, credential-free, and inexpensive.
- Synthetic reference answers, passages, and labels remain evaluation data and
  can never enter verified portfolio knowledge.
- The first baseline describes the local hashed-token adapter, not Vertex AI
  quality and not production recruiter behavior.
- Automated exact-passage support is intentionally conservative. Faithful
  abstractive entailment requires a separately versioned human or model-judge
  protocol before it can become a release gate.
- A reranker or new chunker is added only as a measured experiment against the
  same accepted suite, not because a framework makes it convenient.

## Revisit when

- approved content uses multi-chunk sources that require span-level labels;
- a provider-backed benchmark is approved;
- exact extractive answers are replaced with abstractive synthesis;
- multilingual evaluation is required;
- a human-reviewed or model-judged entailment protocol is versioned; or
- the suite is large enough to require sampled or distributed execution.
