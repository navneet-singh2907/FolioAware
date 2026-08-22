provider "google" {
  project = var.project_id
  region  = var.region

  default_labels = {
    application = "folio-aware"
    environment = var.environment
    managed_by  = "terraform"
  }
}

data "google_project" "current" {
  project_id = var.project_id
}
