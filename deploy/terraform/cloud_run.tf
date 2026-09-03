resource "google_cloud_run_v2_service" "api" {
  count = var.deploy_service ? 1 : 0

  project             = var.project_id
  name                = var.service_name
  location            = var.region
  description         = "A portfolio agent that stays current."
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = true

  scaling {
    min_instance_count = 0
    max_instance_count = 2
  }

  template {
    service_account                  = google_service_account.runtime.email
    timeout                          = "30s"
    max_instance_request_concurrency = 20

    containers {
      image = var.container_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      startup_probe {
        initial_delay_seconds = 1
        timeout_seconds       = 2
        period_seconds        = 2
        failure_threshold     = 10

        http_get {
          path = "/healthz"
          port = 8080
        }
      }

      liveness_probe {
        timeout_seconds   = 2
        period_seconds    = 30
        failure_threshold = 3

        http_get {
          path = "/healthz"
          port = 8080
        }
      }

      env {
        name  = "FOLIOAWARE_ENVIRONMENT"
        value = var.environment
      }

      env {
        name  = "FOLIOAWARE_BACKEND"
        value = "google"
      }

      env {
        name  = "FOLIOAWARE_ALLOWED_ORIGINS"
        value = jsonencode(var.allowed_origins)
      }

      env {
        name  = "FOLIOAWARE_RATE_LIMIT_PER_CLIENT_REQUESTS"
        value = tostring(var.rate_limit_per_client_requests)
      }

      env {
        name  = "FOLIOAWARE_RATE_LIMIT_GLOBAL_REQUESTS"
        value = tostring(var.rate_limit_global_requests)
      }

      env {
        name  = "FOLIOAWARE_RATE_LIMIT_WINDOW_SECONDS"
        value = tostring(var.rate_limit_window_seconds)
      }

      env {
        name  = "FOLIOAWARE_RATE_LIMIT_MAX_CLIENTS"
        value = tostring(var.rate_limit_max_clients)
      }

      env {
        name  = "FOLIOAWARE_ANSWER_CONCURRENCY_LIMIT"
        value = tostring(var.answer_concurrency_limit)
      }

      env {
        name  = "FOLIOAWARE_GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }

      env {
        name  = "FOLIOAWARE_GOOGLE_CLOUD_LOCATION"
        value = var.vertex_location
      }

      env {
        name  = "FOLIOAWARE_FIRESTORE_DATABASE"
        value = google_firestore_database.folioaware.name
      }

      env {
        name  = "FOLIOAWARE_EMBEDDING_MODEL"
        value = var.embedding_model
      }

      env {
        name  = "FOLIOAWARE_EMBEDDING_DIMENSIONS"
        value = tostring(var.embedding_dimensions)
      }

      env {
        name  = "FOLIOAWARE_GENERATION_MODEL"
        value = var.generation_model
      }

      env {
        name  = "FOLIOAWARE_INSIGHT_RULES_PATH"
        value = var.insight_rules_path
      }

      env {
        name = "FOLIOAWARE_SESSION_HASH_SECRET"

        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.session_hash.secret_id
            version = var.session_hash_secret_version
          }
        }
      }

      env {
        name = "FOLIOAWARE_OWNER_REPORT_TOKEN"

        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.owner_report.secret_id
            version = var.owner_report_secret_version
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.required["run.googleapis.com"],
    google_project_iam_member.runtime_firestore,
    google_project_iam_member.runtime_vertex,
    google_secret_manager_secret_iam_member.runtime_owner_report,
    google_secret_manager_secret_iam_member.runtime_session_hash,
  ]

  lifecycle {
    ignore_changes = [template[0].containers[0].image]

    precondition {
      condition     = var.rate_limit_global_requests >= var.rate_limit_per_client_requests
      error_message = "The global request limit cannot be lower than the per-client request limit."
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  count = var.deploy_service ? 1 : 0

  project  = var.project_id
  location = google_cloud_run_v2_service.api[0].location
  name     = google_cloud_run_v2_service.api[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
