# FolioAware Problem Statement

## Summary

Portfolio visitors often want direct, evidence-backed answers about a person's
projects, skills, and experience, but conventional portfolio navigation makes
that evidence difficult to find. Generic chatbots can invent claims, omit
sources, or become stale when portfolio content changes.

FolioAware is a reusable backend for independently hosted portfolio websites.
It answers questions using only explicitly approved portfolio content, cites
the evidence for substantive claims, abstains when evidence is insufficient,
and synchronizes its verified knowledge when approved content changes. In a
separate data path, it records privacy-reduced visitor questions and identifies
recurring interests and knowledge gaps for the portfolio owner.

## Users and needs

### Portfolio visitor

The visitor needs a concise answer that is current, traceable to public
portfolio evidence, and honest when the portfolio does not support a claim.

### Portfolio owner

The owner needs a low-maintenance way to keep answers synchronized with
approved content and understand what visitors repeatedly ask about without
allowing those questions or inferred interests to become portfolio facts.

### Adopting developer

The developer needs an open-source, documented, single-tenant service that can
be connected to an independently hosted portfolio and tested without production
data or live cloud services.

## Required behavior

FolioAware must:

1. Ingest only explicitly approved portfolio content into verified knowledge.
2. Answer visitor questions only when retrieved verified evidence is sufficient.
3. Attach valid citations to every substantive factual answer.
4. Return an explicit knowledge-gap response when evidence is insufficient.
5. Synchronize changed, added, and removed approved content deterministically.
6. Keep verified knowledge versioned so a failed synchronization cannot replace
   the active version.
7. Store privacy-reduced visitor questions separately from verified knowledge.
8. Identify repeated topics, skill-verification questions, and unanswered gaps.
9. Produce owner nudges that distinguish adding existing evidence, building a
   demonstrative project, studying a topic, and leaving a question unanswered.
10. Prevent visitor questions, generated answers, feedback, analytics, and
    inferred interests from being promoted into verified knowledge.
11. Support reuse by other developers without containing private portfolio data
    or visitor analytics.

## Initial release scope

The first release is one portfolio owner per deployment. Its planned runtime is
a Python FastAPI API on Google Cloud Run, backed by Firestore and Vertex AI.
GitHub Actions will use Workload Identity Federation for deployment and
knowledge synchronization. The portfolio frontend remains independently
hosted.

The first end-to-end implementation will be a deliberately small vertical
slice using synthetic portfolio fixtures. It will prove approved-content
validation, evidence retrieval, cited answering, explicit abstention, separate
question storage, and idempotent synchronization before broader product
features are added.

## Out of scope for the first release

- A multi-tenant SaaS platform or shared customer control plane
- Autonomous web browsing or automatic acceptance of facts from public pages
- Promotion of model output, visitor input, or analytics into verified knowledge
- A full owner dashboard or email-notification system in the first slice
- A framework-specific portfolio frontend as a prerequisite for using the API
- LangChain, LangGraph, or another orchestration framework without a demonstrated
  requirement
- Long-lived Google service-account JSON keys
- Production portfolio content, private analytics, or Navneet Singh-specific
  private data in the public repository
- Automatic deployment or creation of billable cloud infrastructure

## Success criteria

The MVP is successful when automated tests demonstrate that:

1. Every substantive answer contains citations that resolve to retrieved,
   active, verified evidence.
2. Unsupported or weakly supported questions return an explicit abstention with
   no fabricated citation.
3. Visitor-derived data cannot be read as or written to verified knowledge.
4. Unchanged content is not re-embedded during synchronization.
5. Changed content is updated and removed content is no longer retrievable.
6. A failed synchronization leaves the previous knowledge version active.
7. A repeated unsupported skill question can produce a knowledge-gap insight
   without creating a skill claim.
8. The API exposes no model or cloud credentials to browser clients.
9. The complete local test, lint, formatting, type-check, and container checks
   pass using synthetic data.
10. Cloud deployment remains an explicit, separately approved action.

## Hard constraints

- Treat visitor input, retrieved text, and model output as untrusted data.
- Keep answering, synchronization, telemetry, analytics, and notifications
  behind replaceable typed interfaces.
- Use deterministic retrieval and response stages around model calls.
- Use direct Google SDK integrations for the MVP unless a concrete need proves
  an orchestration framework valuable.
- Keep secrets out of source control and use short-lived federated credentials
  in CI/CD.
- Configure Cloud Run for request-based billing with zero minimum instances and
  an initial maximum of two instances when deployment is approved.
- Use a reproducible Python dependency lock and automated quality gates.
- Use only synthetic public fixtures in this repository.

## Failure conditions

The product must be considered unsafe or incorrect if any of the following can
occur:

- An answer presents an unsupported substantive claim as fact.
- A citation was not part of the evidence retrieved for that answer.
- A prompt injection in a question or knowledge document can override the
  evidence policy.
- Visitor questions, generated answers, feedback, or inferred interests can
  enter the verified knowledge collection.
- A partial or failed synchronization replaces the active knowledge index.
- Deleted or inactive evidence continues to support new answers.
- Raw credentials or private portfolio/analytics data enter the repository,
  logs, API response, or client bundle.
- Telemetry is described as anonymous while retaining direct identifiers or
  untreated personal information.
- The system creates billable infrastructure without explicit owner approval.

## Open decisions for the architecture phase

The next phase must compare and record decisions for:

1. The canonical approved-content format and approval boundary.
2. Knowledge chunking, version activation, and rollback semantics.
3. Firestore vector-retrieval strategy and relevance thresholds.
4. Vertex AI embedding and generation contracts, including model versioning.
5. Citation validation and model-output rejection behavior.
6. Question sanitization, retention, session correlation, and deletion.
7. Public API abuse controls and owner-only administrative access.
8. Local test adapters versus production Google Cloud adapters.

