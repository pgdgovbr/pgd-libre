# =============================================================================
# Service Accounts do PGD Libre
# =============================================================================

# SA usada pelo GitHub Actions (CI) para fazer build de imagem e deploy ao Cloud Run.
resource "google_service_account" "deploy" {
  account_id   = "${local.prefix}-deploy"
  display_name = "PGD Libre — CI/CD"
  description  = "Usada pelo GitHub Actions para build (Artifact Registry) e deploy (Cloud Run)"

  depends_on = [google_project_service.required]
}

# SA do runtime do Cloud Run (acessa Cloud SQL e Secret Manager).
resource "google_service_account" "runtime" {
  account_id   = "${local.prefix}-runtime"
  display_name = "PGD Libre — Cloud Run runtime"
  description  = "Identidade do Cloud Run service do PGD Libre"

  depends_on = [google_project_service.required]
}

# SA usada pelo Cloud Scheduler para invocar /internal/sync no Cloud Run.
resource "google_service_account" "scheduler" {
  account_id   = "${local.prefix}-scheduler"
  display_name = "PGD Libre — Cloud Scheduler"
  description  = "Identidade dos jobs do Cloud Scheduler do PGD Libre"

  depends_on = [google_project_service.required]
}

# --- Permissões da SA de deploy ---

resource "google_artifact_registry_repository_iam_member" "deploy_writer" {
  location   = google_artifact_registry_repository.pgd_libre.location
  repository = google_artifact_registry_repository.pgd_libre.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_project_iam_member" "deploy_run_developer" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

# NOTA: a SA de deploy também tem `roles/secretmanager.admin` no projeto
# (necessário para gerenciar IAM de secrets via terraform-apply, inclusive
# secrets externos ao workspace — ver `aws-bedrock.tf`). Esse grant NÃO é
# gerenciado aqui porque a própria SA não tem `resourcemanager.projectIamAdmin`
# para editar a policy do projeto — é um bootstrap único feito por humano
# admin via `infra/scripts/bootstrap-deploy-permissions.sh`.

# Permite que a SA de deploy atue como a SA do runtime (necessário para deploy do Cloud Run)
resource "google_service_account_iam_member" "deploy_actas_runtime" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deploy.email}"
}

# --- Permissões da SA do runtime ---

# Acesso a secrets do prefixo pgd-libre-* fica via `secrets.tf` (por secret).

# Cloud SQL client (a app conecta direto via Cloud SQL Auth Proxy/IAM)
resource "google_project_iam_member" "runtime_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# --- Permissões da SA do scheduler ---

# Permite ao Cloud Scheduler invocar o Cloud Run (autenticação via OIDC token)
resource "google_cloud_run_v2_service_iam_member" "scheduler_invoker" {
  project  = google_cloud_run_v2_service.pgd_libre.project
  location = google_cloud_run_v2_service.pgd_libre.location
  name     = google_cloud_run_v2_service.pgd_libre.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

# --- Acesso público ao Cloud Run ---
# Necessário para OAuth: provedores externos (Google) precisam conseguir redirecionar
# o navegador do usuário para /auth/callback/* sem credencial IAM. A app usa JWT em
# cookie httpOnly + middleware User-Agent + RBAC nos resolvers como camadas de defesa
# em profundidade — autorização é responsabilidade da app, não da infra.
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  project  = google_cloud_run_v2_service.pgd_libre.project
  location = google_cloud_run_v2_service.pgd_libre.location
  name     = google_cloud_run_v2_service.pgd_libre.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
