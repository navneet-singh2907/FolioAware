# FolioAware

> A portfolio agent that stays current.

FolioAware is a reusable, evidence-grounded retrieval-augmented generation
(RAG) API for portfolio websites. It answers from owner-approved content,
returns application-owned citations, safely abstains when evidence is weak, and
keeps privacy-reduced visitor-question telemetry outside the knowledge store.

This branch is intentionally a small local vertical slice. It uses synthetic
portfolio fixtures, an in-memory repository, hashed-token embeddings, and an
extractive generator. Those deterministic adapters prove the workflow and
trust boundaries without Google Cloud credentials, network access, or cost.
Firestore and Vertex AI adapters are follow-on work.

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
deployment, service account, or billable infrastructure is created by this
slice.
