#!/usr/bin/env bash
# Bootstrap do bucket de state do Terraform.
# Execução única, com gcloud autenticado no projeto inspire-7-finep.
set -euo pipefail

PROJECT="inspire-7-finep"
BUCKET="pgd-libre-terraform-state"
REGION="southamerica-east1"

if ! gcloud config get-value project --quiet 2>/dev/null | grep -q "${PROJECT}"; then
  echo "ERRO: gcloud não está apontando para ${PROJECT}." >&2
  echo "Rode: gcloud config set project ${PROJECT}" >&2
  exit 1
fi

if gsutil ls -b "gs://${BUCKET}" >/dev/null 2>&1; then
  echo "Bucket gs://${BUCKET} já existe — bootstrap não é necessário."
  exit 0
fi

echo "Criando bucket gs://${BUCKET} em ${REGION}..."
gsutil mb -p "${PROJECT}" -c standard -l "${REGION}" -b on "gs://${BUCKET}"

echo "Habilitando versionamento..."
gsutil versioning set on "gs://${BUCKET}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Aplicando lifecycle (manter últimas 30 versões)..."
gsutil lifecycle set "${SCRIPT_DIR}/state-bucket-lifecycle.json" "gs://${BUCKET}"

echo "OK. Próximo passo:"
echo "  cd terraform"
echo "  terraform init"
echo "  terraform import google_storage_bucket.terraform_state ${BUCKET}"
