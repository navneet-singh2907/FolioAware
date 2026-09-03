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

The local-default sync command validates the approved fixture and prints a JSON
sync result. Its repository is deliberately in memory, so each CLI process
starts clean.
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

## Offline evaluation

Run the versioned synthetic suite through both retrieval and the normal answer
policy without credentials, network calls, or retained visitor telemetry:

```bash
uv run folioaware evaluate \
  --suite evals/fixtures/synthetic-portfolio-v1.yaml \
  --content-root examples/synthetic-portfolio \
  --git-commit abcdef1 \
  --output tmp/evaluation-report.json
```

The command prints byte-stable JSON and optionally writes the identical report
to `--output`. Exit code `0` means every hard evidence gate passed, `1` means
evaluation completed with at least one safety failure, and `2` means the suite,
configuration, or a required dependency was unavailable or invalid. Retrieval
quality metrics describe the synthetic local adapter and are pinned by the
reviewed baseline; they are not production-model claims.

CI compares the same deterministic run with the reviewed baseline:

```bash
uv run folioaware evaluate \
  --git-commit 4770cb3 \
  --distance-threshold 0.72 \
  --top-k 5 \
  --baseline evals/baselines/synthetic-portfolio-v1.json
```

See the [baseline decision](docs/evaluation-baseline.md) for the measured safety
and coverage tradeoff.

## Portfolio widget

The top-level [`widget`](widget/README.md) package provides the portable
`<folio-aware>` custom element. It has no runtime framework dependency, Google
SDK, browser credential, visitor tracking, or persistent storage. An adopter
builds the ES module, hosts it with their own portfolio, and configures the API
deployment with that portfolio's exact CORS origin.

```html
<script type="module" src="/assets/folio-aware.js"></script>
<folio-aware api-base-url="https://api.example"></folio-aware>
```

The widget runtime-validates API responses, renders answers as plain text,
accepts only HTTPS or root-relative citations, and fails closed on malformed
data. See the [widget adopter guide](widget/README.md) for build, theme, local
demo, browser-support, privacy, and accessibility details.

## Quality checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov --cov-report=term-missing
npm --prefix widget ci --ignore-scripts --no-audit --no-fund
npm --prefix widget run check
npm --prefix widget run test:browser
docker build --tag folio-aware:local .
terraform -chdir=deploy/terraform fmt -check -recursive
terraform -chdir=deploy/terraform init -backend=false -lockfile=readonly
terraform -chdir=deploy/terraform validate
terraform -chdir=deploy/terraform test
```

The test suites use no cloud credentials. CI runs the same Python and widget
lint, format, type, test, production-build, browser/accessibility, image-build,
non-root, health, and mocked-infrastructure checks. Terraform initialization
downloads provider plugins but does not access a state backend or Google Cloud.
Playwright downloads a locked Chromium test browser only for the widget job.

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

Cross-origin browser access is denied by default. Configure
`FOLIOAWARE_ALLOWED_ORIGINS` as a JSON array of exact portfolio origins, for
example `["https://portfolio.example"]`. Wildcards are rejected, production
origins must use HTTPS, credentials are disabled, and the middleware permits
only `POST` with `Content-Type`. CORS is a browser policy, not authentication,
rate limiting, bot protection, or a spending limit.

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

## Deployment foundation

The reusable, non-applied Google Cloud definition lives in
[`deploy/terraform`](deploy/terraform/README.md). It describes Cloud Run with
minimum zero and maximum two instances, Firestore indexes, Artifact Registry,
secret containers, least-privilege service accounts, and workflow-scoped
Workload Identity Federation. No service-account JSON keys are used.

Infrastructure validation is offline and automatic; a real plan or apply is
never automatic and requires explicit approval. The reusable deploy workflow
can only build an immutable source commit and update an existing service's
image. A separate reusable sync workflow runs only the approved-content loader,
Vertex embeddings, Firestore copy-on-write activation, and bounded sync history
through its own WIF identity.

See [ADR-0010](docs/adr/0010-terraform-foundation-and-wif.md) and the
[permission map](docs/infrastructure-permissions.md) for the trust boundaries,
bootstrap phases, and Firestore IAM limitation.

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

## Production knowledge synchronization

`folioaware sync --backend google` uses Application Default Credentials and a
sync-only composition root. It requires the Google project, Vertex location,
Firestore database, embedding model/dimensions, and request timeout documented
in `.env.example`. It does not construct generation, telemetry, analytics, or
runtime-secret dependencies.

An adopting portfolio repository can call the reusable workflow after approved
content reaches its protected `main` branch:

```yaml
name: Sync FolioAware knowledge

on:
  push:
    branches: [main]
    paths:
      - "portfolio-content/**"

permissions:
  contents: read
  id-token: write

jobs:
  sync:
    uses: your-org/folio-aware/.github/workflows/sync-reusable.yml@0123456789abcdef0123456789abcdef01234567
    with:
      project_id: example-folio-aware-project
      workload_identity_provider: projects/123456789012/locations/global/workloadIdentityPools/folio-aware-sync/providers/github
      sync_service_account: folio-aware-sync@example-folio-aware-project.iam.gserviceaccount.com
      content_root: portfolio-content
      engine_repository: your-org/folio-aware
      engine_commit: 0123456789abcdef0123456789abcdef01234567
```

Use the same reviewed FolioAware commit in `uses`, `engine_commit`, and the
Terraform `sync_workflow_ref`. The example values are synthetic. Merely adding
this open-source workflow creates no cloud resource and makes no paid call; an
adopter must first apply approved infrastructure and invoke the caller.

See [ADR-0011](docs/adr/0011-production-google-knowledge-sync.md) for why sync
has a separate composition root and how terminal history failures are handled.

## Project documentation

- [Problem statement](docs/problem-statement.md)
- [Architecture and ADR index](docs/architecture.md)
- [Repository structure](docs/repository-structure.md)
- [API and data contracts](docs/api-and-data-contracts.md)
- [Threat model](docs/threat-model.md)
- [Evidence policy](docs/evidence-policy.md)
- [MVP vertical-slice plan](docs/mvp-plan.md)
- [Terraform deployment foundation](deploy/terraform/README.md)
- [Infrastructure permission map](docs/infrastructure-permissions.md)
- [Production Google synchronization decision](docs/adr/0011-production-google-knowledge-sync.md)
- [Portfolio widget adopter guide](widget/README.md)
- [Widget architecture decision](docs/adr/0012-framework-independent-portfolio-widget.md)
- [RAG evaluation harness plan](docs/evaluation-harness-plan.md)
- [Evaluation architecture decision](docs/adr/0013-repository-native-evaluation-harness.md)
- [Accepted synthetic evaluation baseline](docs/evaluation-baseline.md)
- [Portable approved-source schema](schemas/knowledge-source.schema.json)

No real portfolio content or visitor analytics are included. No cloud resource,
deployment, service account, API key, or billable infrastructure is created by
this repository.

## License

FolioAware is open-source software licensed under the
[Apache License 2.0](LICENSE). Portfolio content, deployment configuration, and
visitor analytics supplied by an adopter remain outside this repository and
are not relicensed merely by using FolioAware.
