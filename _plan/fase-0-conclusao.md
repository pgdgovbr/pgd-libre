# Plano — Fechamento da Fase 0 do PGD Libre

## Context

O `_projeto/03-plano-implementacao.md` lista 7 itens não marcados em Fase 0. Após exploração, 4 estão obsoletos ou já feitos (Dockerfile já existe, senha local foi substituída por OAuth, spike foi validado retroativamente pelas Fases 1-2, IaC vive em repo separado) e 3 são pendentes reais (CSP, CI pipeline, AuditLog — este vira decisão explícita de manter manual).

Para o item "GCP/CI setup", o usuário decidiu criar um novo repo `infra/` ao lado do `pgd-libre/` em `/Users/nitai/dev/destaquesgovbr/pgd-libre/`. A infraestrutura vai coexistir no projeto GCP `inspire-7-finep` onde já vive o Destaques Gov BR (cuja IaC está em `/Users/nitai/dev/destaquesgovbr/infra/`). Para evitar colisão, todos os recursos do PGD Libre recebem prefixo `pgd-libre-`, e o terraform state vai num bucket exclusivo.

Decisões já validadas com o usuário:
- AuditLog continua manual (38 call sites carregam contexto semântico que listener perderia)
- Build/deploy (Artifact Registry + Cloud Run via GitHub Actions) entra no plano agora; execução depende do `infra/` provisionar Workload Identity Federation primeiro
- Atualização do plano vira **v0.6**
- Cloud SQL: **instância dedicada** `pgd-libre-postgres` (não compartilhar com Destaques)

---

## Trabalho — 5 entregas

### Entrega 1 — Atualizar `_projeto/03-plano-implementacao.md` (v0.6)

**Arquivo:** `/Users/nitai/dev/destaquesgovbr/pgd-libre/pgd-libre/_projeto/03-plano-implementacao.md`

Mudanças na lista de checkboxes da Fase 0 (linhas ~386-402):

| Item atual | Ação |
|---|---|
| `[ ] Dockerfile baseado em python:3.12-slim-bookworm…` (linha 389) | Marcar `[x]` — Dockerfile já existe na raiz com esse padrão exato |
| `[ ] Middleware CSP nos endpoints /docs e /redoc` (linha 391) | Manter; será marcado após a Entrega 2 |
| `[ ] Recuperação de senha via e-mail` (linha 395) | **Remover linha** + nota v0.6: senha local descartada pela decisão Gov.br/Google OAuth (v0.3) |
| `[ ] Spike de 1 semana…` (linha 399) | **Remover linha** + nota v0.6: stack validada retroativamente pelas Sprints 1.1-2.8 (304 testes verdes) |
| `[ ] GCP/CI setup…` (linha 400) | Reescrever para refletir a separação: CI do código fica em `pgd-libre/.github/workflows/` (Entrega 3); IaC vai para o novo repo `pgd-libre/infra/` (Entrega 5). Reescrever o item como "Repo `infra/` com Terraform e workflows GitOps (Entrega 5 deste plano)" |
| `[ ] Pipeline CI: lint, type check, testes` (linha 401) | Manter; será marcado após Entrega 3 |
| `[ ] AuditLog: middleware/decorator…` (linha 402) | **Remover** + nota v0.6 + adicionar em seção 9 ("Decisões fechadas") |

Adicionar entrada `### Alterações v0.6 — 2026-05-14` em seção 11 listando:
1. Dockerfile já implementado — checkbox marcado
2. Recuperação de senha removida (OAuth-only desde v0.3)
3. Spike removido (validado retroativamente pelas Fases 1-2)
4. AuditLog: decisão explícita de manter manual (ver seção 9)
5. Estrutura de infra: novo repo `infra/` em `/Users/nitai/dev/destaquesgovbr/pgd-libre/infra/`, coexistindo com `destaquesgovbr/infra` no mesmo projeto GCP `inspire-7-finep` via prefixo `pgd-libre-`

Adicionar na seção 9 ("Decisões fechadas"), duas novas linhas:
> | AuditLog | **Chamadas explícitas pelos services** (38 call sites). Listener SQLAlchemy automático foi descartado: perde contexto semântico (APROVAR vs REJEITAR — ambos seriam UPDATE), perde `user`/`ip_address`/`old_values`. |
> | Convenção de nomes GCP | **Prefixo `pgd-libre-`** em todos os recursos (Cloud Run, Cloud SQL, Secret Manager, Artifact Registry, Cloud Scheduler, SAs). Coexistência com Destaques Gov BR (`destaquesgovbr-*`) no mesmo projeto `inspire-7-finep`. Terraform state em bucket exclusivo `pgd-libre-terraform-state`. |

---

### Entrega 2 — Middleware CSP para `/docs` e `/redoc`

**Arquivos:**
- `/Users/nitai/dev/destaquesgovbr/pgd-libre/pgd-libre/src/main.py` — adicionar middleware antes do `require_user_agent`
- `/Users/nitai/dev/destaquesgovbr/pgd-libre/pgd-libre/tests/test_csp.py` — novo teste

**Implementação** (em `src/main.py` antes da linha 37):

```python
@app.middleware("http")
async def csp_for_docs(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/docs", "/redoc")):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' data:"
        )
    return response
```

`'unsafe-inline'` é necessário (Swagger UI injeta script inline). Em produção `/docs` e `/redoc` já são `None` (linhas 21-22) → middleware vira no-op. HSTS, X-Frame-Options etc. ficam para Fase 3.

**Testes:**
1. `GET /docs` retorna header com `default-src 'self'` e `cdn.jsdelivr.net`
2. `GET /healthz` (rota em `src/api/health.py`) **não** tem header CSP

---

### Entrega 3 — Pipeline CI: `.github/workflows/ci.yml` (no repo pgd-libre)

**Arquivo novo:** `/Users/nitai/dev/destaquesgovbr/pgd-libre/pgd-libre/.github/workflows/ci.yml`

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  lint-and-type:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: pyproject.toml
      - run: pip install -e ".[dev]"
      - run: ruff check src tests
      - run: ruff format --check src tests
      - run: mypy src

  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: pgdlibre
          POSTGRES_PASSWORD: pgdlibre
          POSTGRES_DB: pgdlibre
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
    env:
      DATABASE_URL: postgresql+psycopg://pgdlibre:pgdlibre@localhost:5432/pgdlibre
      SECRET_KEY: test-secret-key-for-ci-only
      FRONTEND_URL: http://localhost:3000
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: pyproject.toml
      - run: pip install -e ".[dev]"
      - run: pytest --cov=src --cov-report=term-missing
```

Notas: fixture `db` em `tests/conftest.py:46-59` cria/dropa schema por teste, sem `alembic upgrade`. Verificar/ajustar extra `[dev]` em pyproject.toml. PIP_NO_INPUT do CLAUDE.md local não se aplica no runner.

---

### Entrega 4 — Workflow build/deploy: `.github/workflows/build.yml` (no repo pgd-libre)

**Arquivo novo:** `/Users/nitai/dev/destaquesgovbr/pgd-libre/pgd-libre/.github/workflows/build.yml`

**Pré-requisitos** (providos pela Entrega 5):
- Workload Identity Provider: `projects/<NUMBER>/locations/global/workloadIdentityPools/github-pool/providers/github-provider` (reaproveitado de Destaques)
- Service Account dedicada: `pgd-libre-deploy@inspire-7-finep.iam.gserviceaccount.com` (roles `artifactregistry.writer`, `run.developer`, `iam.serviceAccountUser` na SA runtime)
- Artifact Registry: `southamerica-east1-docker.pkg.dev/inspire-7-finep/pgd-libre/`
- Cloud Run service `pgd-libre` provisionado (pode ser placeholder inicial)

```yaml
name: Build & Deploy
on:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY_PROVIDER }}
          service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}
      - uses: google-github-actions/setup-gcloud@v2
      - run: gcloud auth configure-docker southamerica-east1-docker.pkg.dev
      - name: Build & push
        run: |
          IMAGE=southamerica-east1-docker.pkg.dev/inspire-7-finep/pgd-libre/app:${{ github.sha }}
          docker build -t "$IMAGE" .
          docker push "$IMAGE"
          echo "IMAGE=$IMAGE" >> $GITHUB_ENV
      - name: Deploy Cloud Run
        run: |
          gcloud run deploy pgd-libre \
            --image=$IMAGE \
            --region=southamerica-east1 \
            --project=inspire-7-finep
```

Env vars do Cloud Run permanecem geridas pelo Terraform (feedback memory). O workflow só atualiza imagem. Sem `cloudbuild.yaml` (evita duplicação).

Sequenciamento: criar o arquivo já com `if: false` no job; remover guard quando a Entrega 5 estiver aplicada e os secrets `GCP_WORKLOAD_IDENTITY_PROVIDER` / `GCP_SERVICE_ACCOUNT` configurados no repo.

---

### Entrega 5 — Novo repo `infra/` em `/Users/nitai/dev/destaquesgovbr/pgd-libre/infra/`

Espelha o padrão do `destaquesgovbr/infra` (workflows GitOps, único projeto, ambientes via SA/variáveis e não pastas). Coexistência via prefixo `pgd-libre-` em todos os recursos. Tudo no projeto `inspire-7-finep`, região `southamerica-east1`.

#### 5.1 — Bootstrap manual (uma vez, fora do Terraform)

A criação do bucket de state é circular — não pode estar no próprio Terraform. Roteiro:

```bash
# Com o usuário autenticado (gcloud auth login + auth application-default login):
gcloud config set project inspire-7-finep

gsutil mb -p inspire-7-finep -c standard -l southamerica-east1 \
  -b on gs://pgd-libre-terraform-state

gsutil versioning set on gs://pgd-libre-terraform-state

gsutil lifecycle set scripts/state-bucket-lifecycle.json \
  gs://pgd-libre-terraform-state   # mantém últimas 30 versões
```

Depois do bootstrap, importar o bucket pro Terraform com `terraform import google_storage_bucket.tf_state pgd-libre-terraform-state` e definir `prevent_destroy = true` no resource (mesmo padrão de `destaquesgovbr/infra/terraform/state-bucket.tf`).

#### 5.2 — Estrutura do repo

```
/Users/nitai/dev/destaquesgovbr/pgd-libre/infra/
├── .gitignore
├── .terraform-version           # 1.7 ou mais recente compatível
├── README.md                    # bootstrap, convenções, runbook
├── Makefile                     # comandos comuns (init, fmt, validate, plan)
├── scripts/
│   ├── bootstrap-state-bucket.sh
│   └── state-bucket-lifecycle.json
├── terraform/
│   ├── main.tf                  # backend "gcs" + provider google
│   ├── variables.tf             # project_id, region, project_prefix="pgd-libre"
│   ├── locals.tf                # naming helpers
│   ├── state-bucket.tf          # bucket importado com prevent_destroy
│   ├── apis.tf                  # google_project_service para APIs necessárias
│   ├── artifact-registry.tf     # repo Docker pgd-libre/
│   ├── cloud-sql.tf             # instância pgd-libre-postgres + DB + user + secret
│   ├── secrets.tf               # SYNC_SECRET, SECRET_KEY app, OAuth secrets (Gov.br/Google)
│   ├── cloud-run.tf             # service pgd-libre
│   ├── cloud-scheduler.tf       # job pgd-libre-sync → POST /internal/sync
│   ├── iam.tf                   # SAs: pgd-libre-deploy (CI), pgd-libre-runtime (Cloud Run), pgd-libre-scheduler
│   └── workload-identity.tf     # binding adicional ao pool github-pool já existente
└── .github/workflows/
    ├── terraform-plan.yml       # gatilha em PR; comenta plan no PR
    └── terraform-apply.yml      # gatilha em push para main
```

Decisões implícitas:
- Sem separação de pastas por ambiente (segue padrão Destaques). Para um segundo ambiente futuro, criar workspaces Terraform ou variáveis `environment`.
- `reusable-terraform` (módulos compartilhados do Destaques) **não** será reaproveitado nesta primeira iteração — recursos do PGD Libre são poucos e simples; usar resources direto é mais legível para o time. Reavaliar se a infra crescer.

#### 5.3 — Recursos provisionados

Todos com prefixo `pgd-libre-`. Lista mínima para Fase 0:

| Tipo | Nome | Notas |
|---|---|---|
| `google_storage_bucket` | `pgd-libre-terraform-state` | Importado após bootstrap; `prevent_destroy = true` |
| `google_artifact_registry_repository` | `pgd-libre` | Docker, region southamerica-east1 |
| `google_sql_database_instance` | `pgd-libre-postgres` | PostgreSQL 16, tier `db-custom-1-3840` (1 vCPU, 3.75 GB) inicialmente, backups ativos, PITR ativo |
| `google_sql_database` | `pgdlibre` | Database aplicação |
| `google_sql_user` | `pgdlibre_app` | Password no Secret Manager |
| `google_secret_manager_secret` | `pgd-libre-db-connection-string` | Connection string completa para o Cloud Run montar como env |
| `google_secret_manager_secret` | `pgd-libre-sync-secret` | Valor de `SYNC_SECRET` (header `X-Sync-Secret`); compartilhado com Cloud Scheduler |
| `google_secret_manager_secret` | `pgd-libre-app-secret-key` | JWT signing + Session middleware |
| `google_secret_manager_secret` | `pgd-libre-govbr-client-{id,secret}` | OAuth Gov.br (placeholders até registro no MGI) |
| `google_secret_manager_secret` | `pgd-libre-google-oauth-{id,secret}` | OAuth Google (dev/staging) |
| `google_service_account` | `pgd-libre-deploy` | CI: deploy ao Cloud Run via WIF |
| `google_service_account` | `pgd-libre-runtime` | Runtime do Cloud Run; acessa Cloud SQL e Secret Manager |
| `google_service_account` | `pgd-libre-scheduler` | Identidade do Cloud Scheduler para invocar Cloud Run |
| `google_cloud_run_v2_service` | `pgd-libre` | Imagem inicial placeholder; env vars via Terraform; secrets como volumes/refs |
| `google_cloud_scheduler_job` | `pgd-libre-sync` | Cron `0 3 * * *` (diário 03h) → `POST {cloud-run-url}/internal/sync` com header `X-Sync-Secret` e OIDC token; retry config nativa (max 5, backoff 60s–3600s) |
| `google_iam_workload_identity_pool_provider` binding | n/a — só `google_service_account_iam_member` no provider existente do Destaques | Reaproveita `github-pool/github-provider`. Adiciona principalSet do repo `destaquesgovbr/pgd-libre` à SA `pgd-libre-deploy` |

#### 5.4 — Workflows Terraform (espelhando `destaquesgovbr/infra/.github/workflows/`)

- `terraform-plan.yml`: `on: pull_request` em paths `terraform/**` ou o próprio workflow. Roda `terraform init`, `terraform fmt -check`, `terraform validate`, `terraform plan -no-color`, comenta o plan no PR via `actions/github-script`. Auth via WIF (SA `pgd-libre-deploy` com role `roles/viewer` + `roles/iam.workloadIdentityUser`).
- `terraform-apply.yml`: `on: push` em `main`. Mesma auth. `terraform apply -auto-approve`.
- Permissions mínimas no workflow YAML: `contents: read`, `id-token: write`, `pull-requests: write` (só no plan).

Secrets necessários no repo `destaquesgovbr/pgd-libre-infra` (ou onde o repo for hospedado): `GCP_WORKLOAD_IDENTITY_PROVIDER` (full resource path) e `GCP_SERVICE_ACCOUNT` (email da SA `pgd-libre-deploy`).

#### 5.5 — Sequenciamento da Entrega 5

1. **Bootstrap (manual, com user logado):** `bootstrap-state-bucket.sh` cria o bucket `pgd-libre-terraform-state`. Confirmar que o user vai conectar via `gcloud auth login` quando este passo for executar (conforme prometido).
2. **Inicial Terraform (sem CI ainda):** primeiro `terraform apply` local autenticado com `gcloud auth application-default login`, criando: APIs habilitadas, Artifact Registry, SAs, Cloud SQL, Secret Manager (com valores temporários), Cloud Run com imagem `gcr.io/cloudrun/hello` (placeholder), Cloud Scheduler.
3. **Bind WIF para o repo:** aplicar `workload-identity.tf` adicionando `google_service_account_iam_member` ligando `pgd-libre-deploy` ao principalSet do repo GitHub.
4. **Push secrets para GitHub:** configurar `GCP_WORKLOAD_IDENTITY_PROVIDER` e `GCP_SERVICE_ACCOUNT` no repo `pgd-libre` (não no `infra`).
5. **Validar build.yml:** remover o `if: false` da Entrega 4; push para `main` deve gerar imagem em Artifact Registry e atualizar Cloud Run.
6. **Primeiros segredos reais:** valores de `SYNC_SECRET`, `SECRET_KEY` populados via `gcloud secrets versions add` (não pelo Terraform — Terraform cria o secret resource mas a versão fica fora do state). Documentar no README.
7. **OAuth credentials:** placeholders até registro no Gov.br (próximo passo do plano principal). Google OAuth dev pode ser registrado imediatamente.

---

## Sequenciamento global sugerido

1. **PR1 (Entrega 1):** atualizar plano para v0.6. Trivial, alta clareza.
2. **PR2 (Entrega 2):** CSP middleware + testes. Independente, baixo risco.
3. **PR3 (Entrega 3):** `ci.yml` + ajuste no `pyproject.toml` se necessário. Habilita CI no main e em PRs.
4. **PR4 (Entrega 5, parte 1):** bootstrap do bucket + Terraform inicial sem CI. Pede `gcloud auth` ao user.
5. **PR5 (Entrega 5, parte 2):** workflows do `infra/` (plan + apply).
6. **PR6 (Entrega 4):** `build.yml` com guard removido. Push para main faz primeiro deploy real.

PRs 1-3 independentes. PR4 inicia Entrega 5 e pode ser fatiada conforme conforto.

---

## Verificação end-to-end

**Após Entrega 1:** `grep -c "^- \[x\]" _projeto/03-plano-implementacao.md` mostra um a mais; seção 11 e 9 conferem visualmente.

**Após Entrega 2:**
```bash
source .venv/bin/activate
pytest tests/test_csp.py -v
pytest -q --tb=no                  # 304 + 2 = 306 passed
```
Manual: `uvicorn src.main:app` + `curl -I http://localhost:8000/docs -H "User-Agent: test"` mostra header CSP; `/healthz` não.

**Após Entrega 3:** workflow CI verde no primeiro push (~3 min). Failure intencional: `ruff` no unused import; `pytest` num test falho.

**Após Entrega 5 (parte 1):**
```bash
gsutil ls gs://pgd-libre-terraform-state                         # bucket existe
gcloud sql instances describe pgd-libre-postgres                  # instância online
gcloud secrets list --filter="name~pgd-libre-"                   # secrets criados (sem versões reais ainda)
gcloud run services describe pgd-libre --region=southamerica-east1   # service no ar
gcloud scheduler jobs describe pgd-libre-sync --location=southamerica-east1
gcloud iam service-accounts list --filter="email~pgd-libre-"     # 3 SAs
```

**Após Entrega 5 (parte 2):** abrir PR no `infra/` mexendo num arquivo `.tf` → plan deve aparecer como comentário no PR.

**Após Entrega 4 final:** push em `pgd-libre` para main → workflow `Build & Deploy` verde → nova imagem no Artifact Registry → Cloud Run revision nova ativa. Sanity:
```bash
curl -X POST https://<cloud-run-url>/internal/sync \
  -H "X-Sync-Secret: <valor real do secret>" \
  -H "User-Agent: test"
# {"status":"ok","sucesso":0,"erros":[]} ou {"status":"skipped","motivo":"API_PGD_URL não configurada"}
```

---

## Arquivos críticos

**No repo `pgd-libre`:**
- `_projeto/03-plano-implementacao.md` — Entrega 1
- `src/main.py` — Entrega 2 (região do middleware, linhas 17-44)
- `tests/test_csp.py` — Entrega 2 (novo)
- `.github/workflows/ci.yml` — Entrega 3 (novo)
- `.github/workflows/build.yml` — Entrega 4 (novo, com guard removido após Entrega 5)
- `pyproject.toml` — Entrega 3 (verificar extra `[dev]`)

**No novo repo `infra/` (a criar em `/Users/nitai/dev/destaquesgovbr/pgd-libre/infra/`):**
- `terraform/main.tf`, `variables.tf`, `locals.tf`, `state-bucket.tf`, `apis.tf`, `artifact-registry.tf`, `cloud-sql.tf`, `secrets.tf`, `cloud-run.tf`, `cloud-scheduler.tf`, `iam.tf`, `workload-identity.tf`
- `.github/workflows/terraform-plan.yml`, `.github/workflows/terraform-apply.yml`
- `scripts/bootstrap-state-bucket.sh`, `scripts/state-bucket-lifecycle.json`
- `Makefile`, `README.md`, `.terraform-version`, `.gitignore`

**Referências para reaproveitar (não editar):**
- `/Users/nitai/dev/destaquesgovbr/infra/terraform/main.tf` — backend GCS config
- `/Users/nitai/dev/destaquesgovbr/infra/terraform/state-bucket.tf` — pattern com `prevent_destroy`
- `/Users/nitai/dev/destaquesgovbr/infra/terraform/workload-identity.tf` — pool `github-pool`
- `/Users/nitai/dev/destaquesgovbr/infra/.github/workflows/terraform-apply.yml` — workflow base

---

## Itens fora de escopo (vão para outros planos)

- Fase 3 inteira: HTTPS/HSTS/X-Frame-Options globais, rate limiting, LGPD (retenção/anonimização), observabilidade (logs JSON, Prometheus, alertas), backup/restore documentado, load tests, WCAG 2.1 AA
- RF-025 (CRUD admin de usuários) — diferido no handoff
- Registro do `client_id` Gov.br na plataforma do MGI — depende do usuário; valores reais entram nos secrets quando disponíveis
- Reaproveitamento de módulos `reusable-terraform` do Destaques — adiar até infra crescer
