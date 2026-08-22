# FolioAware

> A portfolio agent that stays current.

FolioAware is a reusable, evidence-grounded retrieval-augmented generation
(RAG) API for portfolio websites. It answers from owner-approved content,
returns application-owned citations, safely abstains when evidence is weak, and
keeps privacy-reduced visitor-question telemetry outside the knowledge store.

The safe default is a local vertical slice using synthetic portfolio fixtures,
an in-memory repository, hashed-token embeddings, and an extractive generator.
Direct Vertex AI and Firestore adapters are also available behind explicit
configuration. Their tests inject fake SDK clients, so development and CI need
no Google Cloud credentials, network calls, or cost.

## What the slice proves

```text
approved manifest -> validate -> embed -> candidate index -> activate
visitor question  -> retrieve active evidence -> evidence gate
                  -> answer + verified citation | knowledge_gap
                  -> redacted question telemetry (separate repository)
```

- Only files explicitly listed in `folioaware.yaml` become verified knowledge.
- A new index is activated only after complete candidate validation.
- Unchanged sources reuse compatible embeddings; failed activation preserves
  the previous version.
- Generation is skipped when retrieval is below the calibrated threshold.
- Model output is untrusted: evidence IDs must belong to the retrieved set and,
  in this first slice, the answer must be an exact extract of cited evidence.
- Citation titles and URLs come from approved application data, never from the
  generator.
- Questions are redacted, optional session IDs are HMAC-pseudonymized, and
  neither answers nor inferred interests enter the knowledge repository.

## Local setup

Requirements: Python 3.12 and
[`uv`](https://docs.astral.sh/uv/getting-started/installation/).

```bash
uv sync --locked --all-groups
uv run folioaware sync \
  --content-root examples/synthetic-portfolio \
  --git-commit abcdef1
uv run uvicorn folioaware.api.main:app --reload
```

The sync command validates the approved fixture and prints a JSON sync result.
Its repository is deliberately in memory, so each CLI process starts clean.
Embedding reuse and rollback behavior are demonstrated by the automated use-case
tests rather than persisted between CLI runs.

Ask an answerable question:

```bash
curl -s http://127.0.0.1:8000/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Did they build a FastAPI service on Cloud Run?"}'
```

Ask about deliberately absent evidence:

```bash
curl -s http://127.0.0.1:8000/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Have they used Kafka?"}'
```

The first response is `answered` with the Project Atlas citation. The second is
`knowledge_gap`, has no citations, and does not call the generator.

## Quality checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov --cov-report=term-missing
docker build --tag folio-aware:local .
```

The test suite is offline and uses no cloud credentials. CI runs the same lint,
format, type, test, image-build, non-root, and health checks.

## Configuration

Copy `.env.example` to `.env` for local overrides. It documents configuration
names but contains no credential. Production mode rejects the development HMAC
secret. The local redactor reduces exposure of common email addresses and phone
numbers; it is not a guarantee of anonymity.

`FOLIOAWARE_BACKEND=local` is the default and never constructs a Google client.
The `google` backend requires an explicit project and generation model. It uses
Application Default Credentials and expects the Firestore database and required
vector/composite index to exist already. Starting FolioAware never provisions
APIs, IAM, indexes, databases, or Cloud Run services.

The Google adapters intentionally preserve the same application ports:

- Vertex embeddings select document/query task types and disable silent input
  truncation.
- Vertex generation requests structured JSON but remains untrusted.
- Firestore vector search filters by active version, public visibility,
  verified status, and active chunks.
- Firestore changes the active knowledge pointer transactionally.
- Sanitized questions are written only to `visitor_questions`.

See [ADR-0008](docs/adr/0008-direct-google-sdk-adapters.md) for the alternatives,
limits, and reasons behind these choices.

## Privacy-safe owner insights

FolioAware can aggregate sanitized questions into a bounded owner report. Topic
aliases come from `examples/synthetic-portfolio/insight-topics.yaml`; they are
classification rules, not portfolio facts. A topic appears only after the
configured repeated-question threshold is reached.

The owner-only endpoint counts questions, pseudonymous sessions,
skill-verification intent, and knowledge gaps, then returns a fixed suggested
action. It persists aggregates separately and has no knowledge-write
dependency. Individual questions and session hashes are never returned.

```bash
curl -s http://127.0.0.1:8000/v1/owner/insights/report \
  -H "Authorization: Bearer $FOLIOAWARE_OWNER_REPORT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"periodStart":"2026-08-01T00:00:00Z","periodEnd":"2026-09-01T00:00:00Z"}'
```

Production rejects the documented development token. Provide the real token at
runtime from a secret store. See [ADR-0009](docs/adr/0009-deterministic-insight-aggregation.md)
for the security boundary and migration tradeoffs.

## Project documentation

- [Problem statement](docs/problem-statement.md)
- [Architecture and ADR index](docs/architecture.md)
- [Repository structure](docs/repository-structure.md)
- [API and data contracts](docs/api-and-data-contracts.md)
- [Threat model](docs/threat-model.md)
- [Evidence policy](docs/evidence-policy.md)
- [MVP vertical-slice plan](docs/mvp-plan.md)
- [Portable approved-source schema](schemas/knowledge-source.schema.json)

No real portfolio content or visitor analytics are included. No cloud resource,
deployment, service account, API key, or billable infrastructure is created by
this repository.

## License

FolioAware is open-source software licensed under the
[Apache License 2.0](LICENSE). Portfolio content, deployment configuration, and
visitor analytics supplied by an adopter remain outside this repository and
are not relicensed merely by using FolioAware.
