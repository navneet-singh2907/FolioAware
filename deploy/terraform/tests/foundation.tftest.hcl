mock_provider "google" {
  override_during = plan

  mock_data "google_project" {
    defaults = {
      number = "123456789012"
    }
  }
}

variables {
  project_id                 = "example-folio-aware-project"
  github_repository_id       = "123456789"
  github_repository_owner_id = "987654321"
  generation_model           = "gemini-2.5-flash"
  allowed_origins            = ["https://portfolio.example"]
  deploy_workflow_ref        = "example-org/folio-aware/.github/workflows/deploy-reusable.yml@0123456789abcdef0123456789abcdef01234567"
  sync_workflow_ref          = "example-org/folio-aware/.github/workflows/sync-reusable.yml@0123456789abcdef0123456789abcdef01234567"
}

run "foundation_is_safe_by_default" {
  command = plan

  assert {
    condition     = length(google_cloud_run_v2_service.api) == 0
    error_message = "Cloud Run must not be created during the foundation phase."
  }

  assert {
    condition     = google_firestore_database.folioaware.delete_protection_state == "DELETE_PROTECTION_ENABLED"
    error_message = "Firestore delete protection must remain enabled."
  }

  assert {
    condition     = google_artifact_registry_repository.images.docker_config[0].immutable_tags
    error_message = "Artifact Registry tags must be immutable."
  }

  assert {
    condition     = strcontains(google_iam_workload_identity_pool_provider.deploy_github.attribute_condition, "assertion.repository_id == '123456789'")
    error_message = "Deploy WIF must restrict the immutable repository ID."
  }

  assert {
    condition     = strcontains(google_iam_workload_identity_pool_provider.deploy_github.attribute_condition, "assertion.job_workflow_ref")
    error_message = "Deploy WIF must restrict the exact reusable workflow."
  }
}

run "service_has_cost_and_safety_guards" {
  command = plan

  variables {
    deploy_service  = true
    container_image = "us-central1-docker.pkg.dev/example-folio-aware-project/folio-aware/api@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  }

  assert {
    condition     = google_cloud_run_v2_service.api[0].scaling[0].min_instance_count == 0
    error_message = "Cloud Run minimum instances must remain zero."
  }

  assert {
    condition     = google_cloud_run_v2_service.api[0].scaling[0].max_instance_count == 2
    error_message = "Cloud Run maximum instances must remain two."
  }

  assert {
    condition     = google_cloud_run_v2_service.api[0].template[0].containers[0].resources[0].cpu_idle
    error_message = "CPU idling must remain enabled for request-based billing."
  }

  assert {
    condition     = google_cloud_run_v2_service.api[0].deletion_protection
    error_message = "Cloud Run deletion protection must remain enabled."
  }

  assert {
    condition = one([
      for environment_variable in google_cloud_run_v2_service.api[0].template[0].containers[0].env :
      environment_variable.value if environment_variable.name == "FOLIOAWARE_ALLOWED_ORIGINS"
    ]) == jsonencode(["https://portfolio.example"])
    error_message = "Cloud Run must receive the exact browser-origin allowlist."
  }

  assert {
    condition = one([
      for environment_variable in google_cloud_run_v2_service.api[0].template[0].containers[0].env :
      environment_variable.value if environment_variable.name == "FOLIOAWARE_RATE_LIMIT_PER_CLIENT_REQUESTS"
    ]) == "10"
    error_message = "Cloud Run must configure the per-client application quota."
  }

  assert {
    condition = one([
      for environment_variable in google_cloud_run_v2_service.api[0].template[0].containers[0].env :
      environment_variable.value if environment_variable.name == "FOLIOAWARE_RATE_LIMIT_GLOBAL_REQUESTS"
    ]) == "100"
    error_message = "Cloud Run must configure the global application quota."
  }

  assert {
    condition = one([
      for environment_variable in google_cloud_run_v2_service.api[0].template[0].containers[0].env :
      environment_variable.value if environment_variable.name == "FOLIOAWARE_RATE_LIMIT_WINDOW_SECONDS"
    ]) == "60"
    error_message = "Cloud Run must configure the application quota window."
  }

  assert {
    condition = one([
      for environment_variable in google_cloud_run_v2_service.api[0].template[0].containers[0].env :
      environment_variable.value if environment_variable.name == "FOLIOAWARE_RATE_LIMIT_MAX_CLIENTS"
    ]) == "10000"
    error_message = "Cloud Run must configure the retained client-bucket bound."
  }

  assert {
    condition = one([
      for environment_variable in google_cloud_run_v2_service.api[0].template[0].containers[0].env :
      environment_variable.value if environment_variable.name == "FOLIOAWARE_ANSWER_CONCURRENCY_LIMIT"
    ]) == "4"
    error_message = "Cloud Run must configure the application concurrency cap."
  }
}

run "invalid_rate_limit_relationship_is_rejected" {
  command = plan

  variables {
    deploy_service                 = true
    container_image                = "us-central1-docker.pkg.dev/example-folio-aware-project/folio-aware/api@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    rate_limit_per_client_requests = 11
    rate_limit_global_requests     = 10
  }

  expect_failures = [google_cloud_run_v2_service.api[0]]
}

run "fractional_rate_limit_value_is_rejected" {
  command = plan

  variables {
    rate_limit_window_seconds = 60.5
  }

  expect_failures = [var.rate_limit_window_seconds]
}

run "insecure_browser_origins_are_rejected" {
  command = plan

  variables {
    allowed_origins = ["http://portfolio.example", "https://*.example"]
  }

  expect_failures = [var.allowed_origins]
}
