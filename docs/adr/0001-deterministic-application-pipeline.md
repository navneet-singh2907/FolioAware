# ADR-0001: Deterministic application pipeline

- Status: Proposed
- Date: 2026-08-20

## Context

The system must ground answers in retrieved evidence and make its refusal and
citation behavior testable. The first release has a small, fixed workflow and
does not require autonomous planning or tools.

## Options considered

1. **Direct SDK calls in a deterministic pipeline.** Lowest operational and
   conceptual complexity; policies remain ordinary typed Python and are easy to
   test. More application code is owned by FolioAware.
2. **An orchestration framework.** Provides ready-made abstractions and tracing,
   but adds dependency churn, hidden control flow, and migration risk before a
   framework-specific need is known.
3. **An autonomous tool-using agent.** Flexible for open-ended research, but its
   variable control flow conflicts with the strict evidence boundary and is
   harder to evaluate and cost-bound.

## Decision

Use direct Google SDK integrations behind typed ports and a fixed pipeline:
validate, embed, retrieve, threshold, generate, validate citations, respond.
No stage may be skipped or reordered by a model.

## Consequences

- Control flow, timeouts, error mapping, and abstention remain application-owned.
- Unit tests can replace every external dependency with an in-memory adapter.
- Prompt, generation schema, embedding model, and policy versions must be
  explicit configuration or stored metadata.
- Reconsider a framework only after a demonstrated requirement, such as several
  branching tool workflows, cannot be met cleanly by the pipeline.

