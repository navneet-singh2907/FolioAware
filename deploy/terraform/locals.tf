locals {
  api_services = toset([
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudresourcemanager.googleapis.com",
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
    "assertion.repository_id == '${var.github_repository_id}'",
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

check "deployment_prerequisites" {
  assert {
    condition = !var.deploy_service || (
      var.container_image != null &&
      can(regex("@sha256:[0-9a-f]{64}$", var.container_image))
    )
    error_message = "deploy_service=true requires an immutable container_image digest."
  }
}
