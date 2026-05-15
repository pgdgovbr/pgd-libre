# PGD Libre — Infra (Terraform / GCP)

Infraestrutura como código do **PGD Libre**, deployada no projeto GCP
`inspire-7-finep`, onde coexiste com o projeto **Destaques Gov BR**.

Para evitar colisão, **todos os recursos do PGD Libre usam o prefixo
`pgd-libre-`** (Cloud Run, Cloud SQL, Secret Manager, Artifact Registry,
Cloud Scheduler, service accounts). O Terraform state vive num bucket
exclusivo: `pgd-libre-terraform-state`.

## Convenções

| Recurso | Nome |
|---|---|
| State bucket | `pgd-libre-terraform-state` |
| Cloud Run service | `pgd-libre` |
| Cloud SQL instance | `pgd-libre-postgres` (PostgreSQL 16, dedicada) |
| Database | `pgdlibre` (na instância dedicada) |
| Database user | `pgdlibre_app` |
| Artifact Registry repo | `pgd-libre` |
| Cloud Scheduler job | `pgd-libre-sync` |
| Service Accounts | `pgd-libre-deploy`, `pgd-libre-runtime`, `pgd-libre-scheduler` |
| Secrets | `pgd-libre-db-connection-string`, `pgd-libre-sync-secret`, `pgd-libre-app-secret-key`, `pgd-libre-govbr-client-{id,secret}`, `pgd-libre-google-oauth-{id,secret}` |

## Bootstrap (uma vez)

Antes do primeiro `terraform init`, o bucket de state precisa existir.
Como a criação dele não pode estar no próprio Terraform (paradoxo), há
um script de bootstrap.

```bash
# Pré-requisito: gcloud autenticado e configurado para inspire-7-finep
gcloud auth login
gcloud auth application-default login
gcloud config set project inspire-7-finep

# Cria o bucket pgd-libre-terraform-state
make bootstrap
```

Depois do bootstrap, importe o bucket para o state:

```bash
cd terraform
terraform init
terraform import google_storage_bucket.terraform_state pgd-libre-terraform-state
```

Sequência típica de aplicação inicial (manual, autenticado):

```bash
make fmt
make validate
make plan
make apply   # cria APIs, Artifact Registry, SAs, Cloud SQL, Secret Manager (sem versões), Cloud Run placeholder, Cloud Scheduler
```

Depois popular as versões dos secrets manualmente (não pelo Terraform):

```bash
echo -n "$(openssl rand -hex 32)" | gcloud secrets versions add pgd-libre-sync-secret --data-file=-
echo -n "$(openssl rand -hex 32)" | gcloud secrets versions add pgd-libre-app-secret-key --data-file=-
# Connection string é populada pelo Terraform via google_sql_user e juntada num secret
# OAuth Gov.br / Google: registrar credenciais e adicionar versões
```

## Workload Identity Federation

Reaproveita o **pool `github-pool`** já existente (criado pelo
[`destaquesgovbr/infra`](https://github.com/destaquesgovbr/infra)). O
arquivo `workload-identity.tf` adiciona apenas um binding ligando a SA
`pgd-libre-deploy` ao repo `destaquesgovbr/pgd-libre` via principalSet.

## Workflows GitOps

| Workflow | Trigger | Ação |
|---|---|---|
| `terraform-plan.yml` | `pull_request` em `terraform/**` | `init` + `fmt -check` + `validate` + `plan`; comenta o plan no PR |
| `terraform-apply.yml` | `push` em `main` (path `terraform/**`) | `init` + `apply -auto-approve` |

Ambos autenticam via WIF (sem JSON keys).

## Próximos passos pós-bootstrap

1. Aplicar o Terraform inicial (manual com gcloud autenticado)
2. Adicionar versões reais aos secrets
3. Configurar secrets do GitHub no repo `destaquesgovbr/pgd-libre`:
   - `GCP_WORKLOAD_IDENTITY_PROVIDER` (path completo do provider)
   - `GCP_SERVICE_ACCOUNT` (email da SA `pgd-libre-deploy`)
4. Remover `if: false` do workflow `build.yml` no repo `pgd-libre`
5. Primeiro push para `main` gera primeira imagem e atualiza Cloud Run

## Recursos não geridos aqui

- Banco de dados/schema dentro do `pgdlibre`: migrations rodam via
  Alembic no startup ou manualmente
- Conteúdo dos secrets (`pgd-libre-*`): valores reais inseridos via
  `gcloud secrets versions add` ou Console GCP
- Imagem do Cloud Run: gerada pelo workflow `build.yml` em
  `destaquesgovbr/pgd-libre` (Artifact Registry → Cloud Run)
