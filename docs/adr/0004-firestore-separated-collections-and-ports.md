# ADR-0004: Firestore with separated collections and ports

- Status: Proposed
- Date: 2026-08-20

## Context

The hosting decision selects Firestore for knowledge, telemetry, sync history,
and insights. The application must remain testable without Google Cloud and
must enforce different write permissions for different data classes.

## Options considered

1. **One general Firestore collection.** Minimal setup, but weakens query,
   retention, IAM, and contamination boundaries.
2. **Separate Firestore collections behind application ports.** Matches the
   chosen platform while allowing least privilege and in-memory tests.
3. **Dedicated vector database plus relational analytics store.** May scale
   retrieval and reporting further, but adds systems, credentials, cost, and
   operational work that the single-tenant MVP does not justify.

## Decision

Use distinct collections for `knowledge_chunks`, `index_versions`, `sync_runs`,
`visitor_questions`, `feedback`, `topic_insights`, and `rate_limits`. Access them
through narrow typed repository ports, with Google adapters in production and
in-memory adapters in tests.

Use Firestore nearest-neighbor search with active-version prefiltering. Start
with a configurable 768-dimensional embedding and cosine distance; calibrate
the distance threshold using evaluations rather than treating top-k presence as
sufficient evidence.

## Consequences

- The selected default fits Firestore's current 2,048-dimension maximum while
  allowing a configurable Vertex embedding output dimension.
- Composite/vector indexes become explicit deployment prerequisites, not
  automatically provisioned side effects of application startup.
- Collection-specific retention and IAM can be applied later without migrating
  a mixed collection.
- Firestore-specific types must not leak into domain or API contracts.
- Revisit the store if corpus size, query latency, filtering, or analytics
  workloads exceed measured Firestore capabilities.

