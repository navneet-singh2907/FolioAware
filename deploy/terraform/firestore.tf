resource "google_firestore_database" "folioaware" {
  project     = var.project_id
  name        = var.firestore_database
  location_id = var.firestore_location
  type        = "FIRESTORE_NATIVE"

  delete_protection_state = "DELETE_PROTECTION_ENABLED"
  deletion_policy         = "ABANDON"

  depends_on = [google_project_service.required["firestore.googleapis.com"]]
}

resource "google_firestore_index" "knowledge_vector" {
  project    = var.project_id
  database   = google_firestore_database.folioaware.name
  collection = "knowledge_chunks"

  fields {
    field_path = "index_version"
    order      = "ASCENDING"
  }

  fields {
    field_path = "active"
    order      = "ASCENDING"
  }

  fields {
    field_path = "visibility"
    order      = "ASCENDING"
  }

  fields {
    field_path = "evidence_status"
    order      = "ASCENDING"
  }

  fields {
    field_path = "__name__"
    order      = "ASCENDING"
  }

  fields {
    field_path = "embedding"

    vector_config {
      dimension = var.embedding_dimensions
      flat {}
    }
  }
}

resource "google_firestore_index" "topic_insight_period" {
  project    = var.project_id
  database   = google_firestore_database.folioaware.name
  collection = "topic_insights"

  fields {
    field_path = "period_start"
    order      = "ASCENDING"
  }

  fields {
    field_path = "period_end"
    order      = "ASCENDING"
  }
}
