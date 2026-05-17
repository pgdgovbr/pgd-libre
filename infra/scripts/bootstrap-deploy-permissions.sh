#!/usr/bin/env bash
# Bootstrap de permissões da SA `pgd-libre-deploy` no projeto GCP.
#
# Estas permissões precisam ser concedidas por um humano com role de
# Project Owner / IAM Admin, porque a própria SA `pgd-libre-deploy` não
# tem `resourcemanager.projectIamAdmin` (e dar isso a ela seria
# overkill — permitiria gerenciar IAM de todo o projeto, incluindo o
# workspace DGB que coexiste no mesmo projeto GCP).
#
# Roles necessárias:
# - roles/run.developer            → já concedida via terraform (iam.tf)
# - roles/artifactregistry.writer  → já concedida via terraform (iam.tf)
# - roles/iam.serviceAccountUser   → já concedida via terraform (iam.tf)
# - roles/secretmanager.admin      → bootstrap (este script). Necessária
#   para gerenciar IAM members em secrets do projeto, inclusive secrets
#   externos ao workspace (ex.: airflow-connections-aws_bedrock).
#
# Idempotente — pode ser rodado múltiplas vezes.
set -euo pipefail

PROJECT="inspire-7-finep"
SA="pgd-libre-deploy@${PROJECT}.iam.gserviceaccount.com"

if ! gcloud config get-value project --quiet 2>/dev/null | grep -q "${PROJECT}"; then
  echo "ERRO: gcloud não está apontando para ${PROJECT}." >&2
  echo "Rode: gcloud config set project ${PROJECT}" >&2
  exit 1
fi

echo "Concedendo roles/secretmanager.admin a ${SA} no projeto ${PROJECT}..."
gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="serviceAccount:${SA}" \
  --role="roles/secretmanager.admin" \
  --condition=None \
  --quiet >/dev/null

echo "OK. Bindings atuais da SA:"
gcloud projects get-iam-policy "${PROJECT}" \
  --flatten="bindings[].members" \
  --filter="bindings.members:${SA}" \
  --format="value(bindings.role)"
