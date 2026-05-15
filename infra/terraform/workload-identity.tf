# =============================================================================
# Workload Identity Federation
# =============================================================================
# O pool `github-pool` já existe (criado pelo repo destaquesgovbr/infra). Aqui:
# 1. Reaproveitamos o pool (data source).
# 2. Criamos um provider PRÓPRIO `github-provider-pgdgovbr` no mesmo pool, com
#    attribute_condition aceitando a org `pgdgovbr` (o provider original do
#    Destaques só aceita `destaquesgovbr`). Isso mantém isolamento conceitual
#    entre os dois projetos sem mexer no state do Destaques.
# 3. Bind da SA `pgd-libre-deploy` ao principalSet do repo no GitHub.
# =============================================================================

data "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-pool"
}

resource "google_iam_workload_identity_pool_provider" "github_pgdgovbr" {
  workload_identity_pool_id          = data.google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider-pgdgovbr"
  display_name                       = "GitHub OIDC — pgdgovbr"
  description                        = "Provider para o repo pgdgovbr/pgd-libre"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  attribute_condition = "assertion.repository_owner == '${var.github_organization}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "deploy_workload_identity" {
  service_account_id = google_service_account.deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${data.google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_organization}/${var.github_repo}"
}

output "github_workload_identity_provider" {
  description = "Full path do WIF Provider para usar em GCP_WORKLOAD_IDENTITY_PROVIDER no GitHub"
  value       = google_iam_workload_identity_pool_provider.github_pgdgovbr.name
}

output "github_deploy_service_account" {
  description = "Email da SA de deploy para usar em GCP_SERVICE_ACCOUNT no GitHub"
  value       = google_service_account.deploy.email
}
