# ADR-0007: Cloud Run and keyless GitHub Actions

- Status: Proposed
- Date: 2026-08-20

## Context

The API has sporadic portfolio traffic and must minimize idle cost and secret
exposure. The frontend is independently hosted, so the answer endpoint must be
browser-accessible while administrative actions remain protected.

## Options considered

1. **Cloud Run plus Workload Identity Federation.** Scales to zero and uses
   short-lived CI credentials, with cold-start and public-endpoint abuse risks.
2. **A continuously running VM/container host with service-account keys.** Gives
   predictable warm latency but increases operations, idle cost, and credential
   risk.
3. **A fully managed agent/search product.** Reduces custom runtime work but
   weakens portability and control over the evidence and data-separation model.

## Decision

Deploy the FastAPI container to Cloud Run only after explicit approval. Use
request-based billing, service-level minimum instances `0`, and service-level
maximum instances `2` initially. The answer endpoint may be unauthenticated for
portfolio use; administrative and sync operations are not exposed as public API
routes.

GitHub Actions authenticates through GitHub OIDC and Google Workload Identity
Federation using short-lived credentials. Trust conditions must restrict the
repository owner, repository, and approved branch/workflow. Use distinct
least-privilege runtime, deployment, and synchronization identities. Do not
create or accept long-lived service-account JSON keys.

## Consequences

- Cold starts are an accepted MVP cost/latency tradeoff.
- CORS restricts browser origins but is not authentication or abuse prevention;
  input limits, timeouts, rate/cost controls, monitoring, and bounded model calls
  are still required.
- Maximum instances is a cost guardrail, not a strict request or spend limit.
- The application cannot rely on local container disk for durable state.
- Infrastructure definitions and workflows may be committed and validated
  locally, but applying them always requires separate approval.

