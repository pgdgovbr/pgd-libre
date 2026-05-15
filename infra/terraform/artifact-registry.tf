# =============================================================================
# Artifact Registry — imagens Docker do PGD Libre
# =============================================================================

resource "google_artifact_registry_repository" "pgd_libre" {
  location      = var.region
  repository_id = local.prefix
  description   = "Imagens Docker do PGD Libre"
  format        = "DOCKER"

  labels = local.common_labels

  depends_on = [google_project_service.required]
}
