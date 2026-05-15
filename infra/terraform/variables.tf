variable "project_id" {
  description = "GCP project ID (compartilhado com Destaques Gov BR)"
  type        = string
  default     = "inspire-7-finep"
}

variable "region" {
  description = "Região padrão para recursos regionais"
  type        = string
  default     = "southamerica-east1"
}

variable "zone" {
  description = "Zona padrão para recursos zonais"
  type        = string
  default     = "southamerica-east1-a"
}

variable "project_prefix" {
  description = "Prefixo aplicado a todos os recursos do PGD Libre, para coexistência com Destaques Gov BR"
  type        = string
  default     = "pgd-libre"
}

variable "github_organization" {
  description = "Organização GitHub que hospeda o repo pgd-libre"
  type        = string
  default     = "pgdgovbr"
}

variable "github_repo" {
  description = "Nome do repositório GitHub do PGD Libre (sem o owner)"
  type        = string
  default     = "pgd-libre"
}

variable "cloud_run_image" {
  description = "Imagem inicial do Cloud Run (placeholder até o primeiro build via GitHub Actions)"
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}
