resource "google_compute_global_address" "public_edge" {
  count = var.enable_public_edge ? 1 : 0

  project      = var.project_id
  name         = "${var.service_name}-edge-ip"
  address_type = "EXTERNAL"
  ip_version   = "IPV4"

  depends_on = [google_project_service.required["compute.googleapis.com"]]

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_compute_region_network_endpoint_group" "cloud_run" {
  count = var.enable_public_edge ? 1 : 0

  project               = var.project_id
  name                  = "${var.service_name}-serverless-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = google_cloud_run_v2_service.api[0].name
  }

  depends_on = [google_project_service.required["compute.googleapis.com"]]
}

resource "google_compute_security_policy" "public_edge" {
  count = var.enable_public_edge ? 1 : 0

  project     = var.project_id
  name        = "${var.service_name}-edge-policy"
  description = "Deployment-wide per-IP admission control for FolioAware."

  rule {
    action      = "throttle"
    priority    = 1000
    description = "Throttle abusive client IPs before requests reach Cloud Run."

    match {
      versioned_expr = "SRC_IPS_V1"

      config {
        src_ip_ranges = ["*"]
      }
    }

    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"

      rate_limit_threshold {
        count        = var.edge_rate_limit_per_ip_requests
        interval_sec = var.edge_rate_limit_window_seconds
      }
    }
  }

  rule {
    action      = "allow"
    priority    = 2147483647
    description = "Default allow after the rate-limit rule."

    match {
      versioned_expr = "SRC_IPS_V1"

      config {
        src_ip_ranges = ["*"]
      }
    }
  }

  depends_on = [google_project_service.required["compute.googleapis.com"]]
}

resource "google_compute_backend_service" "public_edge" {
  count = var.enable_public_edge ? 1 : 0

  project               = var.project_id
  name                  = "${var.service_name}-edge-backend"
  protocol              = "HTTP"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.public_edge[0].id

  backend {
    group = google_compute_region_network_endpoint_group.cloud_run[0].id
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

resource "google_compute_url_map" "https" {
  count = var.enable_public_edge ? 1 : 0

  project         = var.project_id
  name            = "${var.service_name}-https-map"
  default_service = google_compute_backend_service.public_edge[0].id
}

resource "google_compute_managed_ssl_certificate" "api" {
  count = var.enable_public_edge ? 1 : 0

  project = var.project_id
  name    = "${var.service_name}-api-certificate"

  managed {
    domains = [var.api_domain]
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "google_compute_target_https_proxy" "public_edge" {
  count = var.enable_public_edge ? 1 : 0

  project          = var.project_id
  name             = "${var.service_name}-https-proxy"
  url_map          = google_compute_url_map.https[0].id
  ssl_certificates = [google_compute_managed_ssl_certificate.api[0].id]
}

resource "google_compute_global_forwarding_rule" "https" {
  count = var.enable_public_edge ? 1 : 0

  project               = var.project_id
  name                  = "${var.service_name}-https-forwarding-rule"
  ip_address            = google_compute_global_address.public_edge[0].address
  port_range            = "443"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  target                = google_compute_target_https_proxy.public_edge[0].id
}

resource "google_compute_url_map" "http_redirect" {
  count = var.enable_public_edge ? 1 : 0

  project = var.project_id
  name    = "${var.service_name}-http-redirect-map"

  default_url_redirect {
    https_redirect = true
    strip_query    = false
  }
}

resource "google_compute_target_http_proxy" "redirect" {
  count = var.enable_public_edge ? 1 : 0

  project = var.project_id
  name    = "${var.service_name}-http-proxy"
  url_map = google_compute_url_map.http_redirect[0].id
}

resource "google_compute_global_forwarding_rule" "http" {
  count = var.enable_public_edge ? 1 : 0

  project               = var.project_id
  name                  = "${var.service_name}-http-forwarding-rule"
  ip_address            = google_compute_global_address.public_edge[0].address
  port_range            = "80"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  target                = google_compute_target_http_proxy.redirect[0].id
}
