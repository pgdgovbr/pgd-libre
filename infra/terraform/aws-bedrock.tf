# =============================================================================
# AWS Bedrock — feature "Reescrever com IA" no Registro de Execução
# =============================================================================
# Reusa o secret `airflow-connections-aws_bedrock` já mantido no projeto GCP
# (criado e populado pelo workspace DGB — mesmas credenciais usadas pelo
# clipping). O backend faz parsing da URL Airflow em AWS_ACCESS_KEY_ID /
# AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION durante o startup (config.py).
#
# O IAM grant (roles/secretmanager.secretAccessor) é gerenciado FORA deste
# terraform porque o SA do GitHub Actions do pgd-libre não tem permissão de
# setIamPolicy em secrets de outros workspaces. O grant foi aplicado uma vez
# manualmente:
#
#   gcloud --project=inspire-7-finep secrets add-iam-policy-binding \
#     airflow-connections-aws_bedrock \
#     --member="serviceAccount:pgd-libre-runtime@inspire-7-finep.iam.gserviceaccount.com" \
#     --role="roles/secretmanager.secretAccessor"
# =============================================================================

data "google_secret_manager_secret" "aws_bedrock_conn" {
  secret_id = "airflow-connections-aws_bedrock"
}
