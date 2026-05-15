locals {
  prefix = var.project_prefix

  common_labels = {
    project    = "pgd-libre"
    managed_by = "terraform"
  }
}
