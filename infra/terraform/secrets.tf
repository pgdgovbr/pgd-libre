# =============================================================================
# Secret Manager — segredos do PGD Libre
# =============================================================================
# O Terraform cria o RESOURCE de cada secret e a primeira versão para os que
# podem ser derivados em IaC (connection string com a senha gerada por random).
# Para os demais (SYNC_SECRET, SECRET_KEY, OAuth IDs), o resource é criado SEM
# versão — a versão real é adicionada manualmente:
#   echo -n "<valor>" | gcloud secrets versions add <nome> --data-file=-
# =============================================================================

locals {
  secrets_managed = [
    "${local.prefix}-sync-secret",    # X-Sync-Secret header para /internal/sync
    "${local.prefix}-app-secret-key", # SECRET_KEY (JWT + Session middleware)
    "${local.prefix}-govbr-client-id",
    "${local.prefix}-govbr-client-secret",
    "${local.prefix}-google-oauth-client-id",
    "${local.prefix}-google-oauth-client-secret",
  ]
}

# --- Connection string da app: derivada (Terraform cria a versão) ---

resource "google_secret_manager_secret" "db_connection_string" {
  secret_id = "${local.prefix}-db-connection-string"

  replication {
    auto {}
  }

  labels = local.common_labels

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "db_connection_string" {
  secret = google_secret_manager_secret.db_connection_string.id
  secret_data = format(
    "postgresql+psycopg://%s:%s@%s/%s?host=/cloudsql/%s",
    google_sql_user.pgdlibre_app.name,
    random_password.db_app_password.result,
    google_sql_database_instance.pgd_libre.public_ip_address,
    google_sql_database.pgdlibre.name,
    google_sql_database_instance.pgd_libre.connection_name,
  )
}

resource "google_secret_manager_secret_iam_member" "runtime_db_connection" {
  secret_id = google_secret_manager_secret.db_connection_string.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

# --- Demais secrets: resource só (versão entra manualmente para os OAuth) ---

resource "google_secret_manager_secret" "managed" {
  for_each = toset(local.secrets_managed)

  secret_id = each.key

  replication {
    auto {}
  }

  labels = local.common_labels

  depends_on = [google_project_service.required]
}

# Versões iniciais geradas pelo Terraform para os secrets sem origem externa.
# Para os OAuth (Gov.br, Google), o usuário adiciona versões via gcloud depois
# que registrar os clients nos respectivos provedores.

resource "random_password" "sync_secret" {
  length  = 48
  special = false
}

resource "random_password" "app_secret_key" {
  length  = 64
  special = false
}

resource "google_secret_manager_secret_version" "sync_secret" {
  secret      = google_secret_manager_secret.managed["${local.prefix}-sync-secret"].id
  secret_data = random_password.sync_secret.result
}

resource "google_secret_manager_secret_version" "app_secret_key" {
  secret      = google_secret_manager_secret.managed["${local.prefix}-app-secret-key"].id
  secret_data = random_password.app_secret_key.result
}

# Runtime SA pode ler todos os secrets do PGD Libre
resource "google_secret_manager_secret_iam_member" "runtime_access" {
  for_each = toset(local.secrets_managed)

  secret_id = google_secret_manager_secret.managed[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

# Scheduler SA precisa ler apenas o sync-secret
resource "google_secret_manager_secret_iam_member" "scheduler_sync_secret" {
  secret_id = google_secret_manager_secret.managed["${local.prefix}-sync-secret"].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.scheduler.email}"
}
