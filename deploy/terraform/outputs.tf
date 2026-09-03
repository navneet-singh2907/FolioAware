output "artifact_registry_repository" {
  description = "Artifact Registry repository path used by deployment workflows."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "cloud_run_service_uri" {
  description = "Cloud Run service URI, or null while deploy_service is false. IAM and ingress still determine whether it is publicly reachable."
  value       = var.deploy_service ? google_cloud_run_v2_service.api[0].uri : null
}

output "deploy_service_account" {
  description = "Service account impersonated only by the deploy WIF pool."
  value       = google_service_account.deploy.email
}

output "deploy_workload_identity_provider" {
  description = "Full provider name supplied to google-github-actions/auth."
  value       = google_iam_workload_identity_pool_provider.deploy_github.name
}

output "runtime_service_account" {
  description = "Cloud Run runtime service account."
  value       = google_service_account.runtime.email
}

output "sync_service_account" {
  description = "Reserved service account for production knowledge synchronization."
  value       = google_service_account.sync.email
}

output "sync_workload_identity_provider" {
  description = "Full provider name supplied to the reusable sync workflow."
  value       = google_iam_workload_identity_pool_provider.sync_github.name
}
