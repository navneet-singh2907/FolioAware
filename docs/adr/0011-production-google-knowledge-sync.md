# ADR-0011: Production Google Knowledge Synchronization

- Status: Accepted
- Date: 2026-08-23

## Context

The approved-source loader, copy-on-write synchronization use case, Vertex
embedding adapter, and Firestore knowledge adapter already exist. The CLI still
always constructs local in-memory dependencies, so a deployed FolioAware
instance cannot yet synchronize approved portfolio changes into Firestore.

The API's Google composition also constructs generation, telemetry, insight,
and runtime-secret dependencies. Reusing it for synchronization would require
capabilities and configuration the sync service account neither needs nor has.

## Decision

Add a dedicated sync composition root with sync-only settings. Local remains
the safe default. Google mode constructs only:

- the approved local manifest loader;
- a direct Vertex embedding provider;
- the Firestore knowledge repository;
- a separate Firestore sync-history repository; and
- clock and identifier providers.

The sync history writes a bounded `running` record before embeddings or
knowledge writes. Successful and failed terminal states overwrite that record
without source content or exception text. Candidate activation remains the
authoritative atomic knowledge transition. A terminal history-update failure
is logged generically and cannot roll back or falsely invalidate an already
activated knowledge version.

Add a reusable `workflow_call` GitHub Actions workflow. It checks out the
caller's exact content commit and a separately pinned 40-character FolioAware
engine commit, authenticates through the sync-only WIF provider, installs the
locked runtime, and invokes `folioaware sync --backend google`. It has no
deployment, Terraform, generation, telemetry, secret-read, or notification
capability.

The caller repository decides which content paths trigger the workflow. A
merged Git commit is workflow authorization, not evidence approval by itself.
Only sources explicitly listed by the valid `folioaware.yaml` manifest on that
revision enter the synchronization candidate.

## Alternatives considered

### Reuse the API application container

Rejected because it would couple synchronization to generation models,
analytics rules, question repositories, and runtime secrets. That conflicts
with least privilege and makes a non-serving job harder to test and operate.

### Put every Google setting on CLI flags

Rejected because long command lines are easy to log or copy incorrectly and
duplicate environment configuration already used by the API. One backend
override remains explicit; Google SDK settings use validated environment
variables.

### Run synchronization inside Cloud Run startup

Rejected because cold starts are request-serving events, not owner-approved
content events. Multiple instances could race, startup would require write
permissions, and model/database failures could take the public API offline.

### Let GitHub write Firestore documents directly

Rejected because it would duplicate admission, hashing, embedding reuse,
candidate validation, and atomic activation policy outside the application.

## Consequences

- Synchronization and serving retain separate composition and IAM boundaries.
- A content PR merge can automatically request synchronization without a
  long-lived Google key.
- Workflow concurrency reduces overlapping syncs; Firestore's compare-and-set
  activation remains the final race defense.
- The workflow produces Vertex embedding and Firestore operation costs only
  when an adopter explicitly configures and invokes it.
- Stale `running` history records are possible if the terminal audit update
  fails after activation; they are operationally reconcilable and do not
  weaken knowledge correctness.
- The first release continues to support structured YAML/JSON approved sources
  only; general scraping and remote includes remain excluded.

## Revisit when

- synchronization exceeds one Firestore batch;
- chunking creates multiple chunks per source;
- remote content sources are approved;
- stale running-history reconciliation needs automation; or
- content repositories require a different human-approval model.
