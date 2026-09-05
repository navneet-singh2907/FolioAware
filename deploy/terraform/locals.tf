locals {
  api_services = toset([
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "compute.googleapis.com",
    "firestore.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "serviceusage.googleapis.com",
    "sts.googleapis.com",
  ])

  deploy_wif_condition = join(" && ", [
    "assertion.repository_owner_id == '${var.github_repository_owner_id}'",
    "assertion.repository_id == '${var.github_repository_id}'",
    "assertion.ref == '${var.github_ref}'",
    "assertion.job_workflow_ref == '${var.deploy_workflow_ref}'",
  ])

  sync_wif_condition = join(" && ", [
    "assertion.repository_owner_id == '${var.github_repository_owner_id}'",
    "assertion.repository_id == '${coalesce(var.sync_github_repository_id, var.github_repository_id)}'",
    "assertion.ref == '${var.github_ref}'",
    "assertion.job_workflow_ref == '${var.sync_workflow_ref}'",
  ])

  wif_attribute_mapping = {
    "google.subject"                = "assertion.sub"
    "attribute.ref"                 = "assertion.ref"
    "attribute.repository_id"       = "assertion.repository_id"
    "attribute.repository_owner_id" = "assertion.repository_owner_id"
    "attribute.job_workflow_ref"    = "assertion.job_workflow_ref"
  }
}

check "public_edge_prerequisites" {
  assert {
    condition = !var.enable_public_edge || (
      var.deploy_service &&
      var.allow_unauthenticated_invocation &&
      var.api_domain != null
    )
    error_message = "enable_public_edge=true requires deploy_service=true, allow_unauthenticated_invocation=true, and api_domain."
  }

  assert {
    condition     = !var.allow_unauthenticated_invocation || var.enable_public_edge
    error_message = "Unauthenticated invocation is allowed only behind the approved public edge."
  }
}

check "deployment_prerequisites" {
  assert {
    condition = !var.deploy_service || (
      var.container_image != null &&
      can(regex("@sha256:[0-9a-f]{64}$", var.container_image))
    )
    error_message = "deploy_service=true requires an immutable container_image digest."
  }
}
