variable "container_image" {
  description = "Immutable Artifact Registry image URI ending in @sha256:<digest>; required only when deploy_service is true."
  type        = string
  default     = null
  nullable    = true
}

variable "allowed_origins" {
  description = "Exact HTTPS portfolio origins granted browser CORS response access."
  type        = list(string)
  default     = []

  validation {
    condition = (
      length(distinct(var.allowed_origins)) == length(var.allowed_origins) &&
      alltrue([
        for origin in var.allowed_origins :
        trimspace(origin) == origin &&
        !strcontains(origin, "*") &&
        !strcontains(origin, "@") &&
        can(regex("^https://[^/?#]+$", origin))
      ])
    )
    error_message = "allowed_origins must contain unique explicit HTTPS origins."
  }
}

variable "rate_limit_per_client_requests" {
  description = "Maximum public answer requests per ASGI-resolved client in one local window per process."
  type        = number
  default     = 10

  validation {
    condition = (
      floor(var.rate_limit_per_client_requests) == var.rate_limit_per_client_requests &&
      var.rate_limit_per_client_requests >= 1 &&
      var.rate_limit_per_client_requests <= 1000
    )
    error_message = "rate_limit_per_client_requests must be a whole number between 1 and 1000."
  }
}

variable "rate_limit_global_requests" {
  description = "Maximum public answer requests across all clients in one local window per process."
  type        = number
  default     = 100

  validation {
    condition = (
      floor(var.rate_limit_global_requests) == var.rate_limit_global_requests &&
      var.rate_limit_global_requests >= 1 &&
      var.rate_limit_global_requests <= 10000
    )
    error_message = "rate_limit_global_requests must be a whole number between 1 and 10000."
  }
}

variable "rate_limit_window_seconds" {
  description = "Fixed-window duration for in-process public answer quotas."
  type        = number
  default     = 60

  validation {
    condition = (
      floor(var.rate_limit_window_seconds) == var.rate_limit_window_seconds &&
      var.rate_limit_window_seconds >= 1 &&
      var.rate_limit_window_seconds <= 3600
    )
    error_message = "rate_limit_window_seconds must be a whole number between 1 and 3600."
  }
}

variable "rate_limit_max_clients" {
  description = "Maximum in-memory client buckets retained by each process."
  type        = number
  default     = 10000

  validation {
    condition = (
      floor(var.rate_limit_max_clients) == var.rate_limit_max_clients &&
      var.rate_limit_max_clients >= 100 &&
      var.rate_limit_max_clients <= 100000
    )
    error_message = "rate_limit_max_clients must be a whole number between 100 and 100000."
  }
}

variable "answer_concurrency_limit" {
  description = "Maximum answer requests admitted concurrently by each application process."
  type        = number
  default     = 4

  validation {
    condition = (
      floor(var.answer_concurrency_limit) == var.answer_concurrency_limit &&
      var.answer_concurrency_limit >= 1 &&
      var.answer_concurrency_limit <= 100
    )
    error_message = "answer_concurrency_limit must be a whole number between 1 and 100."
  }
}

variable "deploy_service" {
  description = "Whether Terraform should create Cloud Run. Keep false until image and secret versions exist."
  type        = bool
  default     = false
}

variable "allow_unauthenticated_invocation" {
  description = "Whether Cloud Run should grant roles/run.invoker to allUsers. Keep false until approved edge controls prevent direct-URL bypass."
  type        = bool
  default     = false
}

variable "enable_public_edge" {
  description = "Whether to provision the HTTPS load balancer and serverless NEG that form the only public ingress path."
  type        = bool
  default     = false
}

variable "enable_cloud_armor" {
  description = "Whether to attach a Cloud Armor per-IP throttle to the public edge. Disable only when the project has no security-policy quota, and keep application admission controls enabled."
  type        = bool
  default     = true
}

variable "api_domain" {
  description = "DNS hostname served by the public HTTPS edge, without a scheme or path. Required when enable_public_edge is true."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = var.api_domain == null || (
      trimspace(var.api_domain) == var.api_domain &&
      can(regex("^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$", var.api_domain))
    )
    error_message = "api_domain must be a lowercase DNS hostname without a scheme, port, path, or wildcard."
  }
}

variable "edge_rate_limit_per_ip_requests" {
  description = "Maximum requests allowed by Cloud Armor per source IP during one edge rate-limit window."
  type        = number
  default     = 30

  validation {
    condition = (
      floor(var.edge_rate_limit_per_ip_requests) == var.edge_rate_limit_per_ip_requests &&
      var.edge_rate_limit_per_ip_requests >= 1 &&
      var.edge_rate_limit_per_ip_requests <= 10000
    )
    error_message = "edge_rate_limit_per_ip_requests must be a whole number between 1 and 10000."
  }
}

variable "edge_rate_limit_window_seconds" {
  description = "Cloud Armor per-IP rate-limit interval in seconds."
  type        = number
  default     = 60

  validation {
    condition     = contains([10, 30, 60, 120, 180, 240, 300, 600, 900, 1200, 1800, 2700, 3600], var.edge_rate_limit_window_seconds)
    error_message = "edge_rate_limit_window_seconds must be a Cloud Armor-supported interval between 10 and 3600 seconds."
  }
}

variable "deploy_workflow_ref" {
  description = "Exact GitHub OIDC job_workflow_ref allowed to impersonate the deploy identity."
  type        = string

  validation {
    condition     = can(regex("^[^/]+/[^/]+/\\.github/workflows/[^@]+@.+$", var.deploy_workflow_ref))
    error_message = "deploy_workflow_ref must be an exact reusable workflow reference."
  }
}

variable "embedding_dimensions" {
  description = "Vertex embedding dimensions and Firestore vector-index dimensions."
  type        = number
  default     = 768

  validation {
    condition     = var.embedding_dimensions >= 1 && var.embedding_dimensions <= 2048
    error_message = "embedding_dimensions must be between 1 and 2048."
  }
}

variable "embedding_model" {
  description = "Vertex embedding model configured in the API."
  type        = string
  default     = "gemini-embedding-001"
}

variable "environment" {
  description = "Single-tenant deployment environment label."
  type        = string
  default     = "production"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}$", var.environment))
    error_message = "environment must be a lowercase label."
  }
}

variable "firestore_database" {
  description = "Firestore Native database ID. Existing databases must be imported before apply."
  type        = string
  default     = "(default)"
}

variable "firestore_location" {
  description = "Immutable Firestore database location."
  type        = string
  default     = "nam5"
}

variable "generation_model" {
  description = "Explicit Vertex generation model used by FolioAware."
  type        = string

  validation {
    condition     = length(trimspace(var.generation_model)) > 0
    error_message = "generation_model cannot be empty."
  }
}

variable "github_ref" {
  description = "Exact caller Git ref admitted by both WIF providers."
  type        = string
  default     = "refs/heads/main"

  validation {
    condition     = startswith(var.github_ref, "refs/")
    error_message = "github_ref must be a full refs/... value."
  }
}

variable "github_repository_id" {
  description = "Immutable numeric GitHub repository ID of the adopter/deployment repository."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+$", var.github_repository_id))
    error_message = "github_repository_id must contain digits only."
  }
}

variable "github_repository_owner_id" {
  description = "Immutable numeric GitHub owner or organization ID."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+$", var.github_repository_owner_id))
    error_message = "github_repository_owner_id must contain digits only."
  }
}

variable "insight_rules_path" {
  description = "Path inside the image to owner-configured deterministic topic rules."
  type        = string
  default     = "examples/synthetic-portfolio/insight-topics.yaml"
}

variable "owner_report_secret_version" {
  description = "Existing Secret Manager version used for the owner report bearer token."
  type        = string
  default     = "latest"
}

variable "project_id" {
  description = "Google Cloud project ID for one FolioAware deployment."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be a valid Google Cloud project ID."
  }
}

variable "region" {
  description = "Region for Cloud Run and Artifact Registry."
  type        = string
  default     = "us-central1"
}

variable "service_name" {
  description = "Cloud Run service name."
  type        = string
  default     = "folio-aware"

  validation {
    condition     = can(regex("^[a-z]([a-z0-9-]{0,47}[a-z0-9])?$", var.service_name))
    error_message = "service_name must be a valid Cloud Run service name."
  }
}

variable "session_hash_secret_version" {
  description = "Existing Secret Manager version used for telemetry HMAC pseudonymization."
  type        = string
  default     = "latest"
}

variable "sync_workflow_ref" {
  description = "Exact GitHub OIDC job_workflow_ref allowed to impersonate the sync identity."
  type        = string

  validation {
    condition     = can(regex("^[^/]+/[^/]+/\\.github/workflows/[^@]+@.+$", var.sync_workflow_ref))
    error_message = "sync_workflow_ref must be an exact reusable workflow reference."
  }
}

variable "sync_github_repository_id" {
  description = "Immutable numeric GitHub repository ID of the sync caller; defaults to github_repository_id."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.sync_github_repository_id == null || can(regex("^[0-9]+$", var.sync_github_repository_id))
    error_message = "sync_github_repository_id must contain digits only when set."
  }
}

variable "vertex_location" {
  description = "Vertex AI location used by the application."
  type        = string
  default     = "global"
}
