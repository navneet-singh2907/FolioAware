# FolioAware Google Cloud Foundation

This Terraform/OpenTofu-compatible root describes one FolioAware tenant in one
Google Cloud project. Nothing in this directory deploys merely because it is
committed. This project intentionally has no automatic `plan` or `apply` job.

## What Terraform is doing

Terraform is declarative: these files describe the desired end state, and the
provider compares that description with Google Cloud. Its state file records
the mapping between resource addresses in code and real remote resources. That
state is sensitive operational data and must never be committed.

The configuration owns:

- required API enablement;
- one immutable Docker repository;
- one Firestore Native database and the required indexes;
- empty Secret Manager containers, never secret values;
- separate runtime, deploy, and sync service accounts;
- workflow-scoped GitHub OIDC federation; and
- an optional Cloud Run service with zero-to-two scaling and an explicit HTTPS
  portfolio-origin allowlist.

## Why bootstrap has two phases

Cloud Run needs an existing image and populated secret versions, while the
image repository and secret containers are infrastructure. `deploy_service`
breaks that dependency cycle:

1. Foundation phase (`false`, the default): create the repository, database,
   identities, WIF, and empty secret containers.
2. An authorized operator adds two secret versions out of band and publishes
   an image.
3. Private service phase (`true`): provide the immutable `@sha256:` image URI,
   create Cloud Run, and perform an authenticated smoke test. Set
   `allowed_origins` to the exact independently hosted portfolio origins whose
   browser JavaScript may read cross-origin API responses.
4. Public traffic phase: only after approved edge controls prevent direct-URL
   bypass, set `enable_public_edge = true`, provide `api_domain`, and explicitly
   set `allow_unauthenticated_invocation = true`. Terraform then restricts
   Cloud Run ingress to the load-balancer path and grants `roles/run.invoker`
   to `allUsers` only behind that network restriction.

This is a deliberate safety latch, not a feature flag used at runtime.

## Public HTTPS edge

The optional public edge provisions a global static IPv4 address, a serverless
NEG, a global external Application Load Balancer, a Google-managed TLS
certificate, an HTTP-to-HTTPS redirect, and a Cloud Armor per-IP throttle. These
resources are billable even when Cloud Run scales to zero.

Cloud Armor is enabled by default. If Google assigns the project a security
policy quota of zero and denies an increase, set `enable_cloud_armor = false`
and keep the application request and concurrency limits enabled. The load
balancer-only Cloud Run ingress restriction still prevents direct-URL bypass;
the application limits become the active abuse-control layer until the quota is
available.

Configure the adopter-specific values only in ignored `terraform.tfvars`:

```hcl
allowed_origins                  = ["https://portfolio.example", "https://www.portfolio.example"]
enable_public_edge               = true
enable_cloud_armor               = true
api_domain                       = "api.portfolio.example"
allow_unauthenticated_invocation = true
```

After reviewing and applying the saved Terraform plan:

1. Read the `public_edge_ip` output.
2. In the authoritative DNS provider, create an `A` record for the API hostname
   pointing to that exact IPv4 address. Do not alter the portfolio's existing
   apex or `www` records.
3. Wait until the Google-managed certificate reports `ACTIVE`; DNS and
   certificate provisioning are asynchronous.
4. Verify `https://api.portfolio.example/healthz` returns `200`.
5. Verify a direct request to the default `run.app` URL is rejected and does
   not reach the application logs.

The Cloud Armor threshold is controlled by
`edge_rate_limit_per_ip_requests` and `edge_rate_limit_window_seconds`. Keep the
application admission controls enabled as defense in depth.

## Review and offline validation

Install a compatible Terraform CLI, then run:

```shell
terraform -chdir=deploy/terraform fmt -check -recursive
terraform -chdir=deploy/terraform init -backend=false -lockfile=readonly
terraform -chdir=deploy/terraform validate
terraform -chdir=deploy/terraform test
```

`init -backend=false` downloads the pinned provider and prepares local plugin
metadata without connecting to a state backend. `validate` checks configuration
and provider schemas. `test` uses a mocked provider and creates no Google
resources. None of these commands is an authenticated deployment.

## Explicitly approved deployment only

Before any real plan or apply:

1. create a protected, versioned GCS state bucket outside this root;
2. copy `backend.hcl.example` and `terraform.tfvars.example` to ignored local
   files and replace every placeholder;
3. confirm the immutable numeric GitHub owner and repository IDs;
4. pin each reusable workflow reference to a reviewed 40-character commit SHA;
5. import an existing default Firestore database if the project already has
   one; and
6. obtain explicit approval for the target project and proposed changes.

An authenticated operator can then initialize the backend and inspect a saved
plan. Those commands are intentionally not provided as a copy-paste deployment
shortcut because project identity and import requirements must be reviewed.

Never pass secret payloads to Terraform. Add versions directly to the two
created Secret Manager containers through an approved operational process.

## Pre-deployment traffic and spend controls

The service passes bounded application admission settings into each process:
per-client and global fixed-window quotas, retained-client capacity, and an
answer concurrency cap. The defaults are intentionally below Cloud Run's
20-request container concurrency so health and owner operations retain room.
Provider calls time out after 15 seconds, Cloud Run requests after 30 seconds,
instances scale from zero to at most two, and CPU idles between requests.

The application counters are process-local. Before public traffic, an operator
must separately review:

1. whether the ASGI server resolves the expected client address without
   trusting caller-supplied forwarding headers;
2. enabling and verifying the Terraform-managed load balancer, serverless NEG,
   and Cloud Armor rate-based policy for deployment-wide enforcement;
3. confirming the direct Cloud Run URL is restricted and cannot bypass the edge
   policy;
4. billing budgets and alert recipients at meaningful thresholds; and
5. whether an eligible spend-cap budget is appropriate for Cloud Run and Vertex
   AI, including the availability impact when the cap pauses service usage.

An alerts-only budget sends notifications but does not cap spending. None of
these external resources is created by this root or by CI. See
`docs/adr/0014-bounded-public-answer-admission.md` and the linked Google Cloud
documentation before an explicitly approved deployment.

`allow_unauthenticated_invocation` and `enable_public_edge` both default to
`false`. Configuration checks reject unauthenticated invocation without the
edge. Authenticate the first test with the deploy identity, then enable public
invocation only as part of the reviewed edge architecture.

## State and lock files

- Commit `.terraform.lock.hcl`: it records selected provider checksums and makes
  provider installation reproducible.
- Never commit `.terraform/`, `.tfstate`, real `.tfvars`, backend configuration,
  credentials, or `gha-creds-*.json`.
- Protect the remote state bucket with versioning, encryption, least privilege,
  and a separate bootstrap process.

## Adopting the reusable deployment workflow

After the initial Cloud Run service exists, an adopter repository can call
`.github/workflows/deploy-reusable.yml` pinned to a FolioAware commit. The
caller supplies the project, region, repository, service, WIF provider, deploy
service account, and exact FolioAware source commit. Put the caller job behind
a protected GitHub environment when human deployment approval is required.

The workflow obtains short-lived credentials, pushes a uniquely tagged image,
and updates only the Cloud Run image. It cannot run `terraform apply`.

The reusable knowledge workflow is `.github/workflows/sync-reusable.yml`. Its
caller must use the same exact workflow commit configured in
`sync_workflow_ref`; otherwise the WIF provider rejects authentication. It can
write knowledge and sync history through the dedicated sync identity but
cannot deploy Cloud Run, read runtime secrets, or generate visitor answers.
When the sync caller is a different repository from the deployment caller, set
`sync_github_repository_id` to that caller's immutable numeric repository ID;
otherwise it defaults to `github_repository_id`.

## Existing resources and imports

Terraform must import any matching existing resource before it can manage it.
The default Firestore database is the common example because projects may have
created it earlier. Import is not resource creation, but it changes state and
therefore belongs in the separately approved bootstrap procedure.

See `docs/infrastructure-permissions.md` for the permission map and the known
Firestore collection-isolation limitation.
