# ADR-0009: Deterministic, Isolated Insight Aggregation

- Status: Accepted
- Date: 2026-08-22

## Context

FolioAware must identify repeated recruiter interests, skill-verification
questions, and unanswered gaps without treating visitor-derived data as
portfolio evidence. The workflow must be inexpensive, explainable, reusable,
and testable without an LLM or cloud credentials.

## Decision

Use owner-maintained topic aliases and deterministic intent rules over already
sanitized `visitor_questions`. Aggregate only bounded time periods and publish
a topic after it reaches a configurable minimum of at least two questions.
Count distinct pseudonymous sessions only when a session hash exists.

Persist aggregates in the separate `topic_insights` collection. The analytics
use case receives telemetry-read and insight-write ports, but no knowledge
repository. Suggested actions are fixed enum values and are recommendations,
never claims.

Expose the first report as `POST /v1/owner/insights/report`, protected by a
constant-time-compared bearer token supplied through runtime configuration.
Production requires a non-default token of at least 32 characters. The token
must be delivered through a secret store; it is never committed.

## Alternatives considered

### LLM classification

Rejected for the first release. It would add cost, nondeterminism, prompt
injection exposure, and an evaluation burden before the small traffic volume
justifies it.

### Hard-coded technology list

Rejected because FolioAware is reusable. A strict external YAML rule file lets
each deployment choose its own taxonomy without changing application code.

### Public or unauthenticated report

Rejected because even privacy-reduced aggregates reveal visitor interests and
should be visible only to the portfolio owner.

### Immediately use a separate scheduled Cloud Run job

Deferred. A separate identity gives stronger least privilege, but requires
cloud provisioning and operational complexity. The application port boundary
allows that migration later without rewriting aggregation policy.

## Consequences

- Reports are cheap, reproducible, and easy to explain and test.
- Rule maintenance is manual and synonyms not listed by the owner are missed.
- The endpoint can materialize aggregate records, so its runtime identity needs
  telemetry-read and insight-write permissions in Google mode.
- The application bearer token is suitable for this single-owner MVP, not a
  multi-user authentication system.
- No insight, topic, question, or suggested action can enter verified knowledge
  through this workflow.

## Revisit when

- traffic demonstrates that rules miss important intents;
- evaluated model classification materially outperforms deterministic rules;
- a scheduled job or Cloud Run IAM replaces application-token protection; or
- multi-user authorization becomes a product requirement.
