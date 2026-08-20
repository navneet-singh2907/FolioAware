# ADR-0003: Copy-on-write knowledge versions

- Status: Proposed
- Date: 2026-08-20

## Context

Synchronization must be incremental and idempotent, removed claims must stop
appearing, and a partial failure must not corrupt the active knowledge set.

## Options considered

1. **Update active documents in place.** Storage-efficient, but readers can see
   a mixed version and rollback is difficult.
2. **Delete and rebuild the collection.** Simple conceptually, but creates an
   availability gap and loses the previous known-good version.
3. **Build a candidate version and atomically switch an active pointer.** Gives
   consistent reads and rollback at the cost of temporary duplicated storage
   and cleanup logic.

## Decision

Use copy-on-write index versions. A sync calculates stable chunk IDs and hashes,
reuses unchanged embeddings where compatible, writes a complete candidate
version, runs critical validation/evaluations, and changes a single active
version pointer only after success.

## Consequences

- Answer retrieval must prefilter by the active index version and active status.
- An embedding may be reused only when content hash, embedding model, task type,
  output dimension, and normalization contract match.
- Failed candidates remain inactive and are eligible for later cleanup.
- Retain at least the previous successful version for rollback; make broader
  retention configurable.
- Activation requires a Firestore transaction or equivalent compare-and-set to
  prevent concurrent syncs from racing.

