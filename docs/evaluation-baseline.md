# Accepted Synthetic Evaluation Baseline

## Decision

FolioAware's offline local baseline uses a retrieval distance threshold of
`0.72` with `top_k=5`, `local-hash-embedding-v1` at 512 dimensions, and the
`local-extractive-v1` generator.

This is a safety-first baseline for the synthetic local adapter. It is not a
claim about Vertex AI quality, production recruiter traffic, or semantic
retrieval performance on private portfolio content.

## Controlled comparison

The same 24 cases, approved sources, embedding adapter, generator, top-K, and
evidence policy were used for every run. Only the distance threshold changed.

| Threshold | Answer coverage | Unsupported answers | Correct abstentions | Hard gates |
| ---: | ---: | ---: | ---: | :---: |
| 0.60 | 3/12 | 0/12 | 12/12 | Pass |
| 0.65 | 6/12 | 0/12 | 12/12 | Pass |
| 0.70 | 8/12 | 0/12 | 12/12 | Pass |
| **0.72** | **10/12** | **0/12** | **12/12** | **Pass** |
| 0.74 | 10/12 | 1/12 | 11/12 | Fail |
| 0.76 | 11/12 | 1/12 | 11/12 | Fail |
| 0.80 | 12/12 | 4/12 | 8/12 | Fail |
| 0.85 | 12/12 | 6/12 | 6/12 | Fail |

The closest unsupported weak match has distance `0.726138721247417`.
Threshold `0.72` stays below that boundary while answering ten supported
cases. The two supported cases it abstains on have nearest relevant distances
`0.757464374963667` and `0.789181489322108`.

Raising the threshold to recover either case first admits an unsupported
answer. The zero-tolerance unsupported-answer gate therefore takes precedence
over coverage.

## Accepted metrics

| Metric | Count | Value |
| --- | ---: | ---: |
| Retrieval Hit@K | 12/12 | 100% |
| Context Relevance@K | 12 relevant / 36 returned | 33.33% |
| Correct Abstention Rate | 12/12 | 100% |
| Unsupported Answer Rate | 0/12 | 0% |
| Abstention Precision | 12/14 | 85.71% |
| Answer Coverage | 10/12 | 83.33% |
| Citation Membership | 10/10 | 100% |
| Citation Precision | 10/10 | 100% |
| Citation Recall | 10/12 | 83.33% |
| Extractive Support Rate | 10/10 | 100% |

All hard evidence and isolation gates pass. The two answerable abstentions are
retained as visible baseline limitations rather than weakened away.

## Reproducibility

- Suite: `synthetic-portfolio-v1`, 24 balanced cases
- Suite digest:
  `sha256:fb19a8162780baddbc2695d26af75934e6edb8c0e91e14e73fa39e51aebad142`
- Approved-content revision: `4770cb3`
- Approved-content digest:
  `sha256:816d19a2cf278dcc702b951c4369780ad96249716854dcf5d7107c5b5972caae`
- Baseline report: `evals/baselines/synthetic-portfolio-v1.json`

Run the gate locally:

```bash
uv run folioaware evaluate \
  --git-commit 4770cb3 \
  --distance-threshold 0.72 \
  --top-k 5 \
  --baseline evals/baselines/synthetic-portfolio-v1.json
```

The comparator rejects changed suite or content digests, changed evaluation
configuration, failed hard gates, lower higher-is-better metrics, or a higher
unsupported-answer rate. An intentional fixture, policy, model, chunking, or
threshold change requires a reviewed replacement baseline.

## Adversarial review

The suite includes direct prompt injection, invented skills, unsupported
production status, unsupported metrics, a mixed supported/unsupported request,
and weak lexical matches. At the accepted threshold, all 12 unanswerable cases
abstain, including every adversarial and skill-verification negative case.

The baseline remains deliberately limited: three one-chunk fictional sources,
hashed-token embeddings, exact extractive generation, English questions, and
no provider calls. A provider-backed benchmark needs a separately approved
protocol, recorded cost and model version, and its own baseline.
