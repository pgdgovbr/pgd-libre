# =============================================================================
# Cloud SQL — instância dedicada ao PGD Libre
# =============================================================================
# Decisão (v0.6 do plano): instância separada do Destaques (`destaquesgovbr-postgres`)
# para isolamento de manutenção, backups, performance e blast radius.
# =============================================================================

resource "random_password" "db_app_password" {
  length  = 32
  special = false
}

resource "google_sql_database_instance" "pgd_libre" {
  name             = "${local.prefix}-postgres"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    edition           = "ENTERPRISE"
    tier              = "db-custom-1-3840" # 1 vCPU / 3.75 GB — ajustar conforme carga
    availability_type = "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = 20
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = true
      backup_retention_settings {
        retained_backups = 30
      }
    }

    maintenance_window {
      day          = 7 # domingo
      hour         = 4
      update_track = "stable"
    }

    insights_config {
      query_insights_enabled  = true
      record_application_tags = true
      record_client_address   = false
    }

    user_labels = local.common_labels
  }

  deletion_protection = true

  depends_on = [google_project_service.required]
}

resource "google_sql_database" "pgdlibre" {
  name     = "pgdlibre"
  instance = google_sql_database_instance.pgd_libre.name
}

resource "google_sql_user" "pgdlibre_app" {
  name     = "pgdlibre_app"
  instance = google_sql_database_instance.pgd_libre.name
  password = random_password.db_app_password.result
}
