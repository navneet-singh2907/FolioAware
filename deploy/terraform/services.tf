resource "google_project_service" "required" {
  for_each = local.api_services

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.region
  repository_id = "folio-aware"
  description   = "Immutable FolioAware application images"
  format        = "DOCKER"

  docker_config {
    immutable_tags = true
  }

  depends_on = [google_project_service.required["artifactregistry.googleapis.com"]]

  lifecycle {
    prevent_destroy = true
  }
}
