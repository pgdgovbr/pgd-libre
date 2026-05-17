# =============================================================================
# AWS Bedrock — feature "Reescrever com IA" no Registro de Execução
# =============================================================================
# Reusa o secret `airflow-connections-aws_bedrock` já mantido no projeto GCP
# (criado e populado pelo workspace DGB — mesmas credenciais usadas pelo
# clipping). O backend faz parsing da URL Airflow em AWS_ACCESS_KEY_ID /
# AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION durante o startup (config.py).
# =============================================================================

data "google_secret_manager_secret" "aws_bedrock_conn" {
  secret_id = "airflow-connections-aws_bedrock"
}

# Runtime SA do pgd-libre pode ler o secret
resource "google_secret_manager_secret_iam_member" "runtime_aws_bedrock" {
  secret_id = data.google_secret_manager_secret.aws_bedrock_conn.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}
