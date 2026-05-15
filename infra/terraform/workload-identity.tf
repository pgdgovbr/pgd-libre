# =============================================================================
# Workload Identity Federation — binding ao pool existente
# =============================================================================
# O pool `github-pool` e o provider `github-provider` já foram criados pelo
# repo destaquesgovbr/infra. Aqui apenas adicionamos o binding ligando a SA
# `pgd-libre-deploy` ao principalSet do repo do PGD Libre no GitHub.
# =============================================================================

data "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-pool"
}

resource "google_service_account_iam_member" "deploy_workload_identity" {
  service_account_id = google_service_account.deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${data.google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_organization}/${var.github_repo}"
}

# Output útil para configurar os secrets do GitHub no repo `pgd-libre`.
output "github_workload_identity_provider" {
  description = "Full path do WIF Provider para usar em GCP_WORKLOAD_IDENTITY_PROVIDER no GitHub"
  value       = "${data.google_iam_workload_identity_pool.github.name}/providers/github-provider"
}

output "github_deploy_service_account" {
  description = "Email da SA de deploy para usar em GCP_SERVICE_ACCOUNT no GitHub"
  value       = google_service_account.deploy.email
}
