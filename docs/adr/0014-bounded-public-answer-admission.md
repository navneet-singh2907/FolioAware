# ADR-0014: Bounded Public Answer Admission

- Status: Accepted
- Date: 2026-09-03

## Context

`POST /v1/ask` is intentionally public. Exact CORS rules control which browser
origins may read responses, but CORS is not authentication, denial-of-service
protection, or a spending limit. Each admitted question can consume embedding,
Firestore, and generation capacity when the Google backend is selected.

The existing Cloud Run definition caps instances at two, container concurrency
at 20, provider calls at 15 seconds, and requests at 30 seconds. Those bounds
limit one failure mode but do not provide per-caller or global request quotas.

## Options considered

### In-process admission control

Apply deterministic quotas and a non-blocking concurrency cap at the public
answer boundary. This is fast, offline-testable, dependency-free, and protects
each process. It is not a distributed quota: every process and Cloud Run
instance owns independent counters.

### Firestore-backed distributed quota

Store counters transactionally so all instances share one limit. This provides
a stronger global bound, but it adds network latency, contention, cost, and a
new availability dependency before every answer. Client-controlled key churn
would also create durable data unless separately contained.

### Edge-only enforcement

Use a load balancer and Cloud Armor rate-based rules. This is the correct place
for deployment-wide client identification and volumetric protection, but it
requires additional billable infrastructure and does not protect direct service
URLs unless those bypass paths are disabled.

## Decision

Implement in-process admission control for `POST /v1/ask` and retain edge
enforcement as a separately approved deployment control.

Each application process enforces:

- 10 requests per ASGI-resolved client per 60-second fixed window;
- 100 requests across all clients per 60-second fixed window;
- at most 4 answer requests in flight; and
- no more than 10,000 retained client buckets, evicted least-recently-used.

All values are bounded configuration. Quota rejection returns `429
RATE_LIMITED`; capacity rejection returns `503 ANSWER_CAPACITY_EXCEEDED`; both
include an integer `Retry-After` header and a fresh request ID. CORS preflights,
health checks, and owner reports do not consume public answer quota.

The client key is `Request.client.host` after ASGI-server proxy processing. The
application never parses raw `Forwarded` or `X-Forwarded-For` headers because a
public caller can spoof them. Client keys stay only in bounded process memory
and are never logged or persisted.

The quota is charged before concurrency admission, so every attempted answer
counts even when the process is busy. Capacity is always released in a `finally`
block. The application does not wrap synchronous provider work in a cancellable
timeout because cancellation would not stop the worker and could release the
capacity slot early; provider and Cloud Run timeouts remain the hard bounds.

## Consequences

- One noisy peer cannot consume unlimited work from one process.
- Distributed clients or multiple instances can exceed any single-process
  counter, so this is defense in depth rather than perimeter protection.
- Client-key churn can weaken per-client fairness after least-recently-used
  eviction, but it cannot bypass the separate per-process global quota.
- A reverse proxy that is not explicitly trusted may cause multiple visitors to
  share one conservative bucket. Deployment must validate the ASGI client
  address before tuning the per-client value.
- Cloud Armor can add deployment-wide rate-based rules through a serverless NEG;
  the direct Cloud Run URL must then be disabled or restricted to prevent bypass.
- Billing budgets and alerts must be configured before public deployment.
  Alerts-only budgets notify but do not cap spend; eligible spend-cap budgets
  require a separate operator decision and failure-mode review.

## Revisit when

- more than one process or instance must share an exact quota;
- observed traffic proves fixed windows too coarse;
- authenticated visitors support a stronger stable key;
- a load balancer and Cloud Armor are approved; or
- a provider offers a lower-cost or enforceable project-level request quota.

## References

- [Cloud Armor rate limiting](https://docs.cloud.google.com/armor/docs/rate-limiting-overview)
- [Cloud Armor with Cloud Run](https://docs.cloud.google.com/armor/docs/integrating-cloud-armor)
- [Cloud Run concurrency](https://docs.cloud.google.com/run/docs/about-concurrency)
- [Cloud Billing budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [Cloud Billing spend-cap budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps)
