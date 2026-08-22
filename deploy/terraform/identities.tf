resource "google_service_account" "runtime" {
  project      = var.project_id
  account_id   = "folio-aware-runtime"
  display_name = "FolioAware Cloud Run runtime"
  description  = "Runtime identity; no deployment or IAM administration capability."

  depends_on = [google_project_service.required["iam.googleapis.com"]]
}

resource "google_service_account" "deploy" {
  project      = var.project_id
  account_id   = "folio-aware-deploy"
  display_name = "FolioAware GitHub deploy"
  description  = "Short-lived WIF target for image push and Cloud Run image updates."

  depends_on = [google_project_service.required["iam.googleapis.com"]]
}

resource "google_service_account" "sync" {
  project      = var.project_id
  account_id   = "folio-aware-sync"
  display_name = "FolioAware knowledge synchronization"
  description  = "Reserved WIF target for the future production Google sync entry point."

  depends_on = [google_project_service.required["iam.googleapis.com"]]
}

resource "google_project_iam_member" "runtime_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "runtime_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "sync_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.sync.email}"
}

resource "google_project_iam_member" "sync_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.sync.email}"
}

resource "google_project_iam_member" "deploy_cloud_run" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_artifact_registry_repository_iam_member" "deploy_writer" {
  project    = google_artifact_registry_repository.images.project
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.repository_id
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_service_account_iam_member" "deploy_can_attach_runtime" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deploy.email}"
}
