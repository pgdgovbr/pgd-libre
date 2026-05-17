# =============================================================================
# Cloud Scheduler — job de sincronização periódica
# =============================================================================
# Chama POST /internal/sync diariamente às 03h00 BRT.
# Autenticação: OIDC token gerado pela SA `pgd-libre-scheduler` (run.invoker)
# + header X-Sync-Secret lido do Secret Manager.
# Backoff nativo do Scheduler: até 5 retentativas com delays exponenciais.
# =============================================================================

# Lê o valor mais recente do secret. A versão inicial é criada pelo Terraform
# (ver secrets.tf — random_password.sync_secret + google_secret_manager_secret_version.sync_secret);
# se um operador adicionar versões manuais via `gcloud secrets versions add`, este
# data source automaticamente passa a usar a nova "latest" no próximo apply.
data "google_secret_manager_secret_version" "sync_secret_latest" {
  secret = google_secret_manager_secret.managed["${local.prefix}-sync-secret"].id

  depends_on = [google_secret_manager_secret_version.sync_secret]
}

resource "google_cloud_scheduler_job" "sync" {
  name        = "${local.prefix}-sync"
  description = "Dispara POST /internal/sync no Cloud Run pgd-libre (envio à API PGD Central)"
  schedule    = "0 3 * * *" # diário às 03h00 (timezone abaixo)
  time_zone   = "America/Sao_Paulo"
  region      = var.region

  attempt_deadline = "600s"

  retry_config {
    retry_count          = 5
    max_retry_duration   = "3600s"
    min_backoff_duration = "60s"
    max_backoff_duration = "600s"
    max_doublings        = 4
  }

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.pgd_libre.uri}/internal/sync"

    headers = {
      "Content-Type"  = "application/json"
      "User-Agent"    = "cloud-scheduler/pgd-libre"
      "X-Sync-Secret" = data.google_secret_manager_secret_version.sync_secret_latest.secret_data
    }

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = google_cloud_run_v2_service.pgd_libre.uri
    }
  }

  depends_on = [
    google_project_service.required,
    google_cloud_run_v2_service.pgd_libre,
  ]
}
