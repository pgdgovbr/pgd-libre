# =============================================================================
# Cloud Run — pgd-libre
# =============================================================================
# A imagem inicial é um placeholder. O workflow `build.yml` do repo pgd-libre
# atualiza a imagem em cada push para main. Env vars vivem aqui (Terraform);
# o workflow NÃO usa --set-env-vars.
# =============================================================================

resource "google_cloud_run_v2_service" "pgd_libre" {
  name     = local.prefix
  location = var.region

  ingress = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.runtime.email

    scaling {
      min_instance_count = 0
      max_instance_count = 4
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.pgd_libre.connection_name]
      }
    }

    containers {
      image = var.cloud_run_image

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      env {
        # Mantido como "staging" enquanto não há dados reais — habilita /docs e /redoc
        # com Swagger UI. Mudar para "production" quando entrar em uso real.
        name  = "ENVIRONMENT"
        value = "staging"
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_connection_string.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.managed["${local.prefix}-app-secret-key"].secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "SYNC_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.managed["${local.prefix}-sync-secret"].secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "GOVBR_CLIENT_ID"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.managed["${local.prefix}-govbr-client-id"].secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "GOVBR_CLIENT_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.managed["${local.prefix}-govbr-client-secret"].secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "GOOGLE_CLIENT_ID"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.managed["${local.prefix}-google-oauth-client-id"].secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "GOOGLE_CLIENT_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.managed["${local.prefix}-google-oauth-client-secret"].secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "FRONTEND_URL"
        value = "https://pgd-portal-klvx64dufq-rj.a.run.app"
      }
    }
  }

  labels = local.common_labels

  # Ignora mudanças na imagem feitas pelo workflow de deploy
  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }

  depends_on = [
    google_project_service.required,
    google_secret_manager_secret_version.db_connection_string,
  ]
}

output "cloud_run_url" {
  description = "URL pública do Cloud Run service"
  value       = google_cloud_run_v2_service.pgd_libre.uri
}
