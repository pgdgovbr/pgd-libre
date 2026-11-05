# =============================================================================
# Encerramento do PGD Libre — #13
# =============================================================================
# Os recursos foram tirados da configuração e o apply os destrói: Cloud Run,
# Cloud SQL (o usuário tem deletion_policy = ABANDON e o database já saiu do
# state no #16; os dois somem com a instância), Cloud Scheduler, Artifact Registry, secrets `pgd-libre-*` e
# seus IAM, SAs runtime e scheduler, e o IAM member do runtime no secret
# `airflow-connections-aws_bedrock`. O secret é do Destaques Gov.BR e fica.
#
# Os blocos `removed` abaixo só tiram os recursos do state, sem destruir:
#
# - APIs: são compartilhadas com o Destaques Gov.BR no mesmo projeto.
# - Bucket de state: o backend ainda usa; apagado à mão no fechamento.
# - SA de deploy, papel de projeto, vínculo WIF e provider WIF: é a
#   identidade que roda este apply. Removidos à mão no fechamento (Fase 4).
# - Bindings que pedem setIamPolicy que a SA de deploy não tem (projeto,
#   SA runtime, repositório do Artifact Registry). Os dois últimos somem
#   com o recurso dono; o de projeto sai à mão no fechamento.
# =============================================================================

removed {
  from = google_project_service.required
  lifecycle {
    destroy = false
  }
}

removed {
  from = google_storage_bucket.terraform_state
  lifecycle {
    destroy = false
  }
}

removed {
  from = google_service_account.deploy
  lifecycle {
    destroy = false
  }
}

removed {
  from = google_project_iam_member.deploy_run_developer
  lifecycle {
    destroy = false
  }
}

removed {
  from = google_service_account_iam_member.deploy_workload_identity
  lifecycle {
    destroy = false
  }
}

removed {
  from = google_iam_workload_identity_pool_provider.github_pgdgovbr
  lifecycle {
    destroy = false
  }
}

removed {
  from = google_project_iam_member.runtime_sql_client
  lifecycle {
    destroy = false
  }
}

removed {
  from = google_service_account_iam_member.deploy_actas_runtime
  lifecycle {
    destroy = false
  }
}

removed {
  from = google_artifact_registry_repository_iam_member.deploy_writer
  lifecycle {
    destroy = false
  }
}
