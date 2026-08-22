# ADR-0010: Terraform Foundation and Workflow-Scoped WIF

- Status: Accepted
- Date: 2026-08-22

## Context

FolioAware needs a reusable Google Cloud deployment definition without creating
resources during development. The deployment must scale Cloud Run from zero to
at most two instances, avoid service-account keys, preserve secret values
outside source and Terraform state, and work for one portfolio per deployment.

The current cloud synchronization CLI is not production-wired: `folioaware
sync` still composes local adapters. Infrastructure can define its future
identity, but must not advertise a runnable Google synchronization workflow yet.

## Decision

Use a Terraform/OpenTofu-compatible root configuration in `deploy/terraform`.
Terraform owns service enablement, Artifact Registry, Firestore and its indexes,
secret containers, service accounts, IAM, two workflow-specific Workload
Identity Federation pools/providers, and the Cloud Run service.

Use a two-phase variable, `deploy_service`, whose safe default is `false`.
Foundation resources can be reviewed separately. Cloud Run is planned only
after immutable image and populated secret-version prerequisites exist. Secret
payloads are never Terraform variables or resources.

Use distinct identities:

| Identity | Capability |
| --- | --- |
| Runtime | Call Vertex AI, access Firestore data, read two runtime secrets |
| Deploy | Push to one Artifact Registry repository, update Cloud Run, attach only the runtime identity |
| Sync | Call Vertex AI and access Firestore data; reserved for the later production sync entry point |

Use separate WIF pools for deploy and sync. Each provider requires immutable
GitHub repository and owner numeric IDs, the exact branch ref, and the exact
`job_workflow_ref`. Each pool can impersonate only its matching service account.
No service-account key resource exists.

The reusable deploy workflow authenticates through WIF, builds from an explicit
engine repository and immutable commit SHA, pushes an immutable image tag, and
updates only the Cloud Run image. Terraform ignores subsequent image drift so
infrastructure and application-release ownership do not fight each other.

## Firestore IAM limitation

Firestore server-library IAM does not provide collection-level roles.
`roles/datastore.user` includes entity read and write permissions at project
scope. Runtime and sync identities therefore have the same database-level data
permission even though application ports and collections are separated.

This MVP does not claim IAM-enforced collection isolation. A compromised
runtime credential has more Firestore authority than its normal code path uses.
Stronger enforcement requires separate Firestore databases or projects plus
separate application clients, which is a later architecture change.

## Alternatives considered

### Manual `gcloud` scripts

Rejected as the primary definition because drift and review are weaker and
reuse requires procedural copying.

### One WIF pool/provider for every workflow

Rejected because a token admitted for one workflow could reach another service
account binding if both bindings trust the same pool subject. Separate pools
make the trust boundary obvious and independently revocable.

### Put secret values in Terraform

Rejected because sensitive values can remain in state even when variables are
marked sensitive. Terraform creates secret containers only; an authorized
operator adds versions out of band.

### Add the sync workflow now

Rejected because the CLI currently writes only to memory. The sync identity and
trust contract are defined now; execution follows the Google sync composition.

## Consequences

- Merely committing or validating this configuration changes no cloud state.
- A first deployment requires an explicitly approved, authenticated bootstrap.
- State must use a separately bootstrapped protected backend; it is never
  committed.
- Cloud Run accepts cold starts with minimum zero and caps instances at two.
- Request-based billing is represented by CPU idling between requests.
- Public invocation is explicit and must be paired with abuse controls later.
- Application releases and Terraform have clear, non-overlapping image
  ownership after initial creation.

## Revisit when

- Google cloud synchronization is implemented;
- collection-level IAM separation becomes mandatory;
- multiple environments require separate root states;
- an organization policy blocks public Cloud Run invocation; or
- observed load justifies different scaling, concurrency, or billing settings.
