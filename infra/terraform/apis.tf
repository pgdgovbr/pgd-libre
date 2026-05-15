# =============================================================================
# Google Cloud APIs necessárias
# =============================================================================
# As APIs já podem estar habilitadas pelo projeto Destaques Gov BR; o Terraform
# do PGD Libre apenas garante (idempotente) que continuam habilitadas.
# =============================================================================

resource "google_project_service" "required" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudscheduler.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "servicenetworking.googleapis.com",
  ])

  service            = each.key
  disable_on_destroy = false
}
