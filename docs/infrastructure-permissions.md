# Infrastructure and Permission Map

## Scope

This document describes what the Terraform configuration would manage after an
explicitly approved `apply`. The repository does not contain a project ID,
billing account, secret value, portfolio content, analytics, or Terraform
state.

## Resource flow

```text
approved operator
  -> terraform foundation
     -> required Google APIs
     -> Firestore + indexes
     -> Artifact Registry
     -> empty Secret Manager containers
     -> runtime/deploy/sync service accounts
     -> deploy WIF pool/provider
     -> sync WIF pool/provider

approved deploy workflow
  -> GitHub OIDC token
  -> deploy WIF provider
  -> temporary deploy service-account credentials
  -> push immutable image
  -> update Cloud Run image

Cloud Run runtime
  -> Vertex AI
  -> Firestore
  -> two runtime secret versions
```

## Identities

### Runtime service account

- `roles/aiplatform.user` on the project
- `roles/datastore.user` on the project
- `roles/secretmanager.secretAccessor` on only the session-hash and owner-report
  secret containers

It receives no Artifact Registry write, Cloud Run administration, IAM
administration, or service-account impersonation role.

### Deploy service account

- `roles/run.developer` on the project
- `roles/artifactregistry.writer` on one repository
- `roles/iam.serviceAccountUser` on only the runtime service account

It receives no Firestore data, Vertex AI, secret accessor, project IAM admin, or
service-account key role.

### Sync service account

- `roles/aiplatform.user` on the project
- `roles/datastore.user` on the project

It receives no Cloud Run administration, Artifact Registry write, secret
access, or runtime service-account impersonation role. It remains unused until
the Google synchronization entry point exists.

## WIF admission

Deploy and sync use separate pools and providers. Each provider checks all of:

1. immutable GitHub owner numeric ID;
2. immutable GitHub repository numeric ID;
3. exact Git ref, initially `refs/heads/main`; and
4. exact reusable-workflow `job_workflow_ref`.

The GitHub job receives only `contents: read` and `id-token: write`. WIF
exchanges the signed OIDC assertion for short-lived credentials. No JSON key is
created or stored in GitHub.

## Known limitation

Firestore's server-side IAM role is database/project scoped rather than
collection scoped. Both runtime and sync identities use `roles/datastore.user`.
The code's dependency-injection and repository boundaries prevent the normal
runtime path from writing knowledge, but IAM alone does not. Separate databases
or projects are required to close that residual risk.

## Apply boundary

The following require separate explicit approval and authenticated operator
credentials:

- `terraform plan` against a real project;
- `terraform apply`;
- API enablement;
- Firestore database or index creation;
- secret-version insertion;
- image push;
- Cloud Run creation or update; and
- any IAM or WIF change.

`terraform fmt`, `terraform init -backend=false`, `terraform validate`, and
mock-provider tests do not create Google Cloud resources.
