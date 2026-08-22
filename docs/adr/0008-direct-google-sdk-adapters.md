# ADR-0008: Direct Google SDK adapters with offline contract tests

- Status: Accepted
- Date: 2026-08-22

## Context

The local vertical slice proved FolioAware's application workflow with
deterministic adapters. Production composition now needs Vertex AI for
embeddings and generation and Firestore for vector knowledge and sanitized
question telemetry. This change must not require live credentials in tests or
provision cloud resources as an application side effect.

## Options considered

1. **Direct `google-genai` and `google-cloud-firestore` SDKs.** Small adapter
   surface, explicit requests, and straightforward fake-client tests.
2. **LangChain or LangGraph wrappers.** Broader integrations and orchestration,
   but FolioAware has a fixed pipeline and gains no required capability from an
   additional framework.
3. **Handwritten REST clients.** Maximum wire-level control, but duplicates
   authentication, serialization, retry, and API-evolution work already owned
   by Google's supported libraries.

## Decision

Use the direct Google SDKs behind the existing application ports.

- `google-genai` uses the Vertex AI backend, explicit project and location,
  stable API `v1`, a bounded timeout, and one request attempt.
- Embeddings set `RETRIEVAL_DOCUMENT` or `RETRIEVAL_QUERY`, request a configured
  dimension no larger than Firestore's 2,048-dimension limit, and disable
  silent truncation.
- Generation supplies no tools, uses temperature zero, requests structured
  JSON, and receives only the bounded question/evidence contract. Structured
  output remains untrusted and is revalidated by Pydantic and the application
  evidence policy.
- Firestore uses separate `knowledge_chunks`, `index_versions`, and
  `visitor_questions` collections plus a fixed `system/knowledge` active
  pointer. Candidate activation compares and changes the pointer in one
  transaction.
- SDK clients are constructor-injected. Unit and contract tests use fakes and
  make no network or credential calls.
- `local` remains the default backend. Selecting `google` requires an explicit
  project and generation model. Authentication uses Application Default
  Credentials; no service-account key file is supported by configuration.

## Consequences

- A deployed environment must already have the required Firestore database,
  vector/composite index, APIs, and least-privilege identity. The application
  does not create them.
- Vendor exceptions are chained internally but translated to stable domain
  errors so public responses never expose Google payloads or identifiers.
- Firestore candidate staging is deliberately limited to one 500-write batch
  in this release: at most 499 chunks plus the version document. Larger corpora
  require a later resumable staging design before this limit can be raised.
- The exact generation model remains deployment configuration rather than a
  hard-coded product claim, allowing controlled model evaluation and upgrades.

## Verification

Offline tests must prove task-type selection, no silent truncation, structured
generation, safe error translation, vector filters, transactional pointer
comparison, batch limits, telemetry separation, and zero client calls during
dependency composition.
