resource "google_secret_manager_secret" "session_hash" {
  project   = var.project_id
  secret_id = "folio-aware-session-hash"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required["secretmanager.googleapis.com"]]

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_secret_manager_secret" "owner_report" {
  project   = var.project_id
  secret_id = "folio-aware-owner-report-token"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required["secretmanager.googleapis.com"]]

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_secret_manager_secret_iam_member" "runtime_session_hash" {
  project   = google_secret_manager_secret.session_hash.project
  secret_id = google_secret_manager_secret.session_hash.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "runtime_owner_report" {
  project   = google_secret_manager_secret.owner_report.project
  secret_id = google_secret_manager_secret.owner_report.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}
