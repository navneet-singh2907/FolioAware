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
- an optional Cloud Run service with zero-to-two scaling.

## Why bootstrap has two phases

Cloud Run needs an existing image and populated secret versions, while the
image repository and secret containers are infrastructure. `deploy_service`
breaks that dependency cycle:

1. Foundation phase (`false`, the default): create the repository, database,
   identities, WIF, and empty secret containers.
2. An authorized operator adds two secret versions out of band and publishes
   an image.
3. Service phase (`true`): provide the immutable `@sha256:` image URI and create
   Cloud Run.

This is a deliberate safety latch, not a feature flag used at runtime.

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

## Existing resources and imports

Terraform must import any matching existing resource before it can manage it.
The default Firestore database is the common example because projects may have
created it earlier. Import is not resource creation, but it changes state and
therefore belongs in the separately approved bootstrap procedure.

See `docs/infrastructure-permissions.md` for the permission map and the known
Firestore collection-isolation limitation.
