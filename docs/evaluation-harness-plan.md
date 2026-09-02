# RAG Evaluation Harness Plan

## Problem statement

FolioAware needs a reproducible way to determine whether a retrieval or policy
change improves evidence quality without making the agent more willing to
answer unsupported questions. Individual tests and cosine distances are not a
quality baseline. The harness must expose noisy context, missed evidence,
false sufficiency, citation mistakes, and over-abstention using only synthetic
public data.

## Scope and success criteria

The first release will:

1. load a strictly validated, versioned synthetic evaluation suite;
2. build the existing synthetic knowledge index entirely in memory;
3. record the top-K structurally eligible candidates before the distance gate;
4. run the normal evidence-gated answer use case without external services;
5. calculate deterministic retrieval, abstention, and citation metrics;
6. emit a stable JSON report with configuration and case-level diagnostics;
7. fail with a non-zero exit code when a hard evidence invariant fails; and
8. run in CI without Google credentials, network calls, or billable resources.

This branch will not introduce semantic chunking, reranking, an LLM judge,
Vertex evaluation calls, production thresholds, private portfolio questions,
or resume claims. Those are experiments that require the accepted baseline.

## Dataset contract

The canonical suite is YAML validated through strict Pydantic models. Unknown
fields fail validation. The first public suite will contain at least 24 cases,
balanced between answerable and unanswerable questions, using only the three
synthetic portfolio sources.

```yaml
schemaVersion: 1
suiteId: synthetic-portfolio-v1
description: Offline evidence and abstention baseline.
policyVersion: evidence-policy-v1
cases:
  - caseId: atlas-cloud-run-paraphrase
    question: Where was Project Atlas deployed?
    expectedStatus: answered
    referenceAnswer: Project Atlas was deployed to Google Cloud Run.
    relevantPassages:
      - sourceId: project-atlas
        text: It was packaged with Docker and deployed to Google Cloud Run.
    requiredCitationSourceIds:
      - project-atlas
    tags:
      - answerable
      - paraphrase
      - deployment

  - caseId: unsupported-kafka-skill
    question: Has the developer used Apache Kafka?
    expectedStatus: knowledge_gap
    relevantPassages: []
    requiredCitationSourceIds: []
    tags:
      - unanswerable
      - skill-verification
```

Contract rules:

- `caseId` and `suiteId` are unique lowercase kebab-case identifiers.
- Questions use the public 3–500 character contract after normalization.
- `answered` requires a reference answer, at least one relevant passage, and at
  least one required citation source.
- `knowledge_gap` forbids a reference answer, relevant passages, and required
  citations.
- Every relevant passage must occur in the referenced approved synthetic
  source after whitespace normalization.
- Required citation sources must be represented by relevant passages.
- Tags use a bounded vocabulary initially covering answerability, paraphrases,
  skill verification, metrics, dates, deployment, weak matches, multi-part
  questions, and adversarial input.
- Reference answers and labels are evaluator-only. They are never supplied to
  retrieval or generation and never synchronized as verified knowledge.

## Evaluation planes

### Retrieval plane

For every case, embed the question and request the same ranked top-K candidates
from the active in-memory knowledge version. Record candidate evidence ID,
source ID, rank, distance, threshold eligibility, and relevance label.

The retrieval plane observes candidates before the distance threshold so it
can show whether a correct passage was retrieved but rejected, or whether the
retriever returned only distractors.

### Answer plane

Run the normal `AnswerQuestion` use case with the same active version,
threshold, top-K, deterministic generation adapter, and a discard-only question
repository. Record final status, citation source IDs, generation call count,
and safe failure code. Do not persist evaluation questions as visitor
analytics.

## Exact metric definitions

Let `A` be answerable cases, `U` be unanswerable cases, `R_q,K` be the first K
retrieved candidates for case `q`, and `rel(q, r)` be 1 when candidate `r`
contains an annotated relevant passage from the annotated source, otherwise 0.

### Retrieval Hit@K

```text
Hit@K = (1 / |A|) * sum over q in A of any(rel(q, r) for r in R_q,K)
```

This answers: “Did at least one supporting passage appear in the first K?” It
does not reveal how much irrelevant context accompanied that passage.

### Context Relevance@K

For each answerable case:

```text
case relevance = relevant candidates in R_q,K / candidates returned in R_q,K
Context Relevance@K = mean(case relevance over A)
```

An answerable case with one relevant chunk and three distractors scores 0.25,
even though Hit@4 is 1. This is the primary noise-to-signal metric. Empty
candidate lists score 0. The report also publishes counts so a mean cannot hide
a small dataset.

The harness uses the name `Context Relevance@K` for this direct ratio. It does
not call it “Context Precision,” which is used inconsistently across evaluation
libraries for both this ratio and ranking-weighted average precision. A future
ranking-weighted metric must receive a separate name and formula.

### Correct Abstention Rate and Unsupported Answer Rate

```text
Correct Abstention Rate = unanswerable cases returned as knowledge_gap / |U|
Unsupported Answer Rate = unanswerable cases returned as answered / |U|
```

These sum to 1 in the two-status MVP. “Abstention accuracy” will not be used as
an ambiguous label.

### Abstention Precision

```text
Abstention Precision = correctly abstained unanswerable cases
                       / all cases returned as knowledge_gap
```

This catches a system that appears safe only because it also refuses many
answerable questions. If no case is predicted as a gap, the metric is 0.

### Answer Coverage

```text
Answer Coverage = answerable cases returned as answered / |A|
```

Coverage is reported beside safety metrics and can never compensate for an
unsupported answer.

### Citation Membership, Precision, and Recall

```text
Citation Membership = cited sources that were in threshold-eligible retrieved
                      evidence / all cited sources
Citation Precision  = cited sources annotated relevant / all cited sources
Citation Recall     = required citation sources returned / all required sources
```

Metrics are micro-averaged with numerator and denominator counts in the report.
An answered case without a citation is a hard failure. A knowledge gap with a
citation is also a hard failure.

### Extractive Support Rate

```text
Extractive Support Rate = answered cases whose complete answer is an exact
                          normalized substring of cited evidence
                          / all answered cases
```

This matches the current MVP generation contract. It must be renamed or
replaced—not silently reused—if FolioAware later permits abstractive answers.

## Gates and baseline policy

Hard gates apply immediately:

| Invariant | Required result |
| --- | ---: |
| Suite and source-reference validation | 100% |
| Unsupported Answer Rate | 0% |
| Citation Membership | 100% |
| Answered responses with citations | 100% |
| Knowledge gaps without citations | 100% |
| Extractive Support Rate | 100% |
| Evaluation-to-knowledge/analytics contamination tests | 100% pass |

Hit@K, Context Relevance@K, Answer Coverage, Abstention Precision, Citation
Precision, and Citation Recall are baseline metrics, not invented release
targets. The first complete 24+ case run will be reviewed and committed as the
accepted local baseline. After acceptance, deterministic CI runs must not fall
below that baseline without an explicit fixture, model, chunking, threshold, or
policy change and an updated comparison report.

Safety gates are never lowered to improve coverage. Aspirational percentages
or resume claims may be stated only after a controlled before/after run on the
same suite and configuration, with case counts included.

## Report contract

The CLI will print JSON to standard output and optionally write an explicitly
requested report path. The stable report contains:

- report and suite schema versions plus a suite content digest;
- evidence-policy version and synthetic content Git revision/digest;
- embedding model, dimensions, top-K, distance threshold, and generator ID;
- aggregate metric numerators, denominators, and decimal values;
- tag-partition metrics, especially skill-verification and adversarial cases;
- per-case expected/actual status and pass/failure reasons;
- ranked evidence IDs, source IDs, distances, relevance, and eligibility;
- citation source IDs and generation call count; and
- hard-gate results and overall pass/fail status.

The deterministic report excludes timestamps, random request IDs, machine
paths, credentials, and raw private data so identical inputs produce an
identical accepted baseline.

Exit codes:

- `0`: suite valid and all configured hard gates pass;
- `1`: evaluation completed but one or more gates failed;
- `2`: invalid suite, configuration, or unavailable required dependency.

## Planned implementation sequence

### Commit 1: Decision and contracts

Record ADR-0013 and this plan. No evaluator behavior or dependency changes.

### Commit 2: Typed suite and synthetic cases

Add strict evaluation models, safe loader, source-reference validation, and at
least 24 balanced public cases with unit tests.

### Commit 3: Retrieval metrics

Add the retrieval runner, exact relevance matching, Hit@K, Context Relevance@K,
case diagnostics, and metric boundary tests.

### Commit 4: Answer, citation, and report slice

Run the normal answer policy with discard-only telemetry; calculate abstention,
coverage, citation, and extractive-support metrics; expose the offline CLI and
stable JSON report.

### Commit 5: Baseline and CI gate

Commit the reviewed deterministic local baseline, run it in CI, document
comparison workflow, perform adversarial review, and update repository and
threat-model ownership. Do not implement a reranker or new chunker here.

## Acceptance criteria

The branch is complete when:

1. at least 24 balanced synthetic cases pass strict schema and source checks;
2. every metric has unit tests for empty, perfect, mixed, and invalid inputs;
3. the CLI produces byte-stable JSON for identical inputs;
4. case diagnostics distinguish retrieval miss, threshold rejection,
   over-abstention, unsupported answer, and citation failure;
5. hard gates fail closed and return the documented exit code;
6. the accepted baseline is generated only from public synthetic data;
7. CI runs offline with no Google credential or provider call;
8. existing Python, widget, container, and Terraform checks remain green; and
9. no cloud resource, deployment, package publication, or billable call occurs.

## Interview framing

The key design statement is:

> “I separated retrieval evaluation from final-answer evaluation. Hit@K tells
> me whether supporting evidence was found, Context Relevance tells me how much
> distractor context surrounded it, and abstention/citation metrics tell me
> whether the policy used that evidence safely. I establish the baseline before
> tuning, so any claimed improvement is reproducible rather than anecdotal.”
