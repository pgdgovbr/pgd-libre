# =============================================================================
# Terraform state bucket
# =============================================================================
# O bucket é criado fora do Terraform (via scripts/bootstrap-state-bucket.sh)
# para resolver o paradoxo de "criar a casa enquanto se mora nela".
# Depois do bootstrap, este resource é importado:
#   terraform import google_storage_bucket.terraform_state pgd-libre-terraform-state
# =============================================================================

resource "google_storage_bucket" "terraform_state" {
  name     = "${local.prefix}-terraform-state"
  location = var.region
  project  = var.project_id

  versioning {
    enabled = true
  }

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      num_newer_versions = 30
    }
  }

  lifecycle {
    prevent_destroy = true
  }

  labels = local.common_labels
}
