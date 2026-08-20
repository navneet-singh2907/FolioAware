# ADR-0006: Privacy-reduced telemetry as a separate data plane

- Status: Proposed
- Date: 2026-08-20

## Context

Questions reveal recruiter interests but can contain personal information.
Calling arbitrary free text anonymous would overstate the privacy guarantee.
Analytics must never become a fact-ingestion route.

## Options considered

1. **Store raw requests and network metadata.** Maximizes analysis but creates
   unnecessary privacy and breach risk.
2. **Store only aggregate counters.** Strong privacy, but prevents redaction
   review, topic reprocessing, and useful knowledge-gap analysis.
3. **Store redacted question text with pseudonymous, rotating session hashes
   and finite retention.** Preserves MVP utility while reducing, not eliminating,
   identification risk.

## Decision

Store privacy-reduced question records in `visitor_questions`, never raw IP
addresses or raw browser identifiers. Redact common direct identifiers before
persistence, derive session hashes with a rotating server-side secret, attach
an expiry time, and keep configurable retention. Describe the data as redacted
or privacy-reduced rather than guaranteed anonymous.

Analytics writes only `topic_insights`; it has no knowledge-repository write
capability. Owner nudges recommend actions but never assert new skills or facts.

## Consequences

- Telemetry persistence failure must not cause an otherwise valid answer to
  become an unsupported answer; the failure is recorded through safe metrics.
- Redaction has false positives and false negatives and requires tests and
  documented limitations.
- Retention, deletion, consent language, and applicable privacy obligations must
  be finalized before a production deployment.
- Cross-deployment tracking and durable identity graphs are prohibited in the
  first release.

