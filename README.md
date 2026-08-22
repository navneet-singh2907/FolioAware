# FolioAware

> A portfolio agent that stays current.

FolioAware is a reusable, evidence-grounded retrieval-augmented generation
(RAG) service for portfolio websites. It answers visitor questions from
owner-approved portfolio content, cites the evidence behind substantive
claims, and keeps visitor-interest telemetry separate from verified facts.

The product definition is documented in
[`docs/problem-statement.md`](docs/problem-statement.md). The proposed system
boundaries and architecture decisions are indexed in
[`docs/architecture.md`](docs/architecture.md).
The planned MVP layout and dependency rules are documented in
[`docs/repository-structure.md`](docs/repository-structure.md).
The proposed HTTP, persistence, model, and port boundaries are documented in
[`docs/api-and-data-contracts.md`](docs/api-and-data-contracts.md).
Security risks and required controls are documented in
[`docs/threat-model.md`](docs/threat-model.md), while claim admission,
sufficiency, citation, and abstention rules are defined in
[`docs/evidence-policy.md`](docs/evidence-policy.md).
The scope, sequence, tests, and acceptance criteria for the first local working
slice are defined in [`docs/mvp-plan.md`](docs/mvp-plan.md).

No cloud resources are provisioned by this repository at this stage.
