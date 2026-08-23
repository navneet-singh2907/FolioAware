resource "google_iam_workload_identity_pool" "deploy" {
  project                   = var.project_id
  workload_identity_pool_id = "folio-aware-deploy"
  display_name              = "FolioAware deploy workflows"
  description               = "Admits only the configured deploy reusable workflow."

  depends_on = [
    google_project_service.required["iam.googleapis.com"],
    google_project_service.required["iamcredentials.googleapis.com"],
    google_project_service.required["sts.googleapis.com"],
  ]
}

resource "google_iam_workload_identity_pool_provider" "deploy_github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.deploy.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub deploy OIDC"
  description                        = "Exact repository IDs, ref, and reusable deploy workflow only."

  attribute_mapping   = local.wif_attribute_mapping
  attribute_condition = local.deploy_wif_condition

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "deploy_wif" {
  service_account_id = google_service_account.deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.deploy.name}/*"
}

resource "google_iam_workload_identity_pool" "sync" {
  project                   = var.project_id
  workload_identity_pool_id = "folio-aware-sync"
  display_name              = "FolioAware sync workflows"
  description               = "Reserved for the configured knowledge-sync reusable workflow."

  depends_on = [
    google_project_service.required["iam.googleapis.com"],
    google_project_service.required["iamcredentials.googleapis.com"],
    google_project_service.required["sts.googleapis.com"],
  ]
}

resource "google_iam_workload_identity_pool_provider" "sync_github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.sync.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub sync OIDC"
  description                        = "Exact repository IDs, ref, and future reusable sync workflow only."

  attribute_mapping   = local.wif_attribute_mapping
  attribute_condition = local.sync_wif_condition

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "sync_wif" {
  service_account_id = google_service_account.sync.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.sync.name}/*"
}
