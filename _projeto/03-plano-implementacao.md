# Plano de Implementação — PGD Libre

**Versão:** 0.6 — 2026-05-14  
**Escopo principal:** Plataforma na ponta (instalada no órgão)  
**Stack base:** Python + GraphQL  
**Horizontes futuros:** Aplicativo móvel · API PGD Central 2.0 · Analytics central

---

## 1. Visão de Arquitetura

### 1.1 Princípios

- **Implantabilidade acima de tudo:** o órgão deve conseguir instalar com `docker compose up`. Zero dependência de infraestrutura do governo para rodar.
- **Compliance por design:** o sistema nasce com o contrato da API PGD Central embutido; a submissão mensal é um detalhe de implementação, não uma afterthought.
- **API-first:** o backend expõe GraphQL como interface única; o frontend web, o app móvel e integrações de terceiros consomem a mesma API.
- **Auditabilidade:** dados nunca são deletados; há rastreabilidade completa de mudanças.

### 1.2 Diagrama de Componentes (plataforma na ponta)

```
┌─────────────────────────────────────────────────────────┐
│                    Órgão Federal                        │
│                                                         │
│  ┌──────────┐   ┌───────────────────────────────────┐  │
│  │  Browser │   │         PGD Libre                 │  │
│  │  (Web UI)│◄──┤                                   │  │
│  └──────────┘   │  ┌──────────────────────────────┐ │  │
│                 │  │  Backend (Python + GraphQL)   │ │  │
│  ┌──────────┐   │  │                              │ │  │
│  │ App Móvel│◄──┤  │  ┌──────────┐ ┌───────────┐ │ │  │
│  │(futuro)  │   │  │  │ GraphQL  │ │  Workers  │ │ │  │
│  └──────────┘   │  │  │  Layer   │ │(agendados)│ │ │  │
│                 │  │  └────┬─────┘ └─────┬─────┘ │ │  │
│  ┌──────────┐   │  │       │             │        │ │  │
│  │ Sistemas │   │  │  ┌────▼─────────────▼──────┐ │ │  │
│  │ Legados  │◄──┤  │  │   Serviço de Domínio    │ │ │  │
│  │ (webhooks│   │  │  │  (regras de negócio)    │ │ │  │
│  │  futuros)│   │  │  └────────────┬────────────┘ │ │  │
│  └──────────┘   │  │               │               │ │  │
│                 │  │  ┌────────────▼────────────┐  │ │  │
│                 │  │  │  PostgreSQL (dados +    │  │ │  │
│                 │  │  │  audit log)             │  │ │  │
│                 │  │  └─────────────────────────┘  │ │  │
│                 │  └──────────────────────────────┘ │  │
│                 └───────────────────────────────────┘  │
│                              │ HTTPS                   │
└──────────────────────────────┼─────────────────────────┘
                               │
              ┌────────────────▼───────────────┐
              │      API PGD Central (MGI)      │
              │  api.pgd.gov.br (referência)    │
              └─────────────────────────────────┘
```

### 1.3 Separação de Responsabilidades

| Camada | Responsabilidade |
|--------|-----------------|
| **GraphQL Layer** | Resolvers, autenticação JWT, autorização RBAC por resolver |
| **Domain Services** | Regras de negócio, validações, orquestração de workflows |
| **Repository / ORM** | Persistência (SQLAlchemy async) |
| **Sync HTTP endpoint** | Endpoint interno `POST /internal/sync` protegido por shared secret, disparado periodicamente pelo Cloud Scheduler para envio à API PGD Central; notificações por e-mail e lembretes de prazo seguem o mesmo padrão (endpoint interno + cron externo) |
| **Web UI** | Interface responsiva (HTML/CSS/JS ou framework SPA) |

---

### 1.4 Metodologia de Desenvolvimento — TDD

Todo código de produção é precedido por testes que falham (**Red → Green → Refactor**). Nenhum PR é aceito sem cobertura de teste para o comportamento que introduz.

**Estrutura de testes:**

```
tests/
├── conftest.py          # Fixtures compartilhadas: db (real PostgreSQL), client (httpx ASGI),
│                        # persist_user(), set_auth_cookie()
├── test_health.py       # TC-TX: User-Agent guard, health, GraphQL básico
├── test_auth_deps.py    # TC-M06: JWT create/decode, get_optional_user
├── test_auth_router.py  # TC-M06: /auth/* endpoints
├── test_graphql.py      # TC-M06: queries GraphQL autenticadas
├── test_permissions.py  # TC-M06: classes IsAuthenticated / IsAdmin / etc. (unit)
├── test_models.py       # modelos SQLAlchemy: defaults, constraints, enums
└── test_<módulo>.py     # um arquivo por sprint (ver Fase 1)
```

**Tipos de teste:**
- **Unitário** (sem I/O): funções puras, classes de permissão, lógica de domínio isolada
- **Integração HTTP** (`client` + DB real): endpoints FastAPI/GraphQL testados de ponta a ponta via httpx ASGI
- Sem camada E2E separada no backend — os testes de integração HTTP já cobrem o contrato da API

**Fixture `db`:** cria todas as tabelas antes do teste, faz rollback e drop depois. Cada teste começa com schema limpo.

**Critério de "done" para cada item dos sprints:** o teste que o cobre está verde no CI (`pytest` passa; `mypy src` sem erros).

**Código já implementado (Fase 0):** testes retroativamente escritos e passando — ver `tests/test_*.py`.

---

## 2. Comparativo de Stacks GraphQL Python

A decisão de stack é relevante porque afeta DX do time, capacidade de geração de schema para documentação e facilidade de integração com ferramentas de auditoria.

### 2.1 Opção A — Strawberry + FastAPI

**Paradigma:** Code-first (schema gerado a partir de type hints Python)

```python
import strawberry
from strawberry.fastapi import GraphQLRouter

@strawberry.type
class PlanoTrabalho:
    id: strawberry.ID
    status: StatusPlanoTrabalhoEnum
    carga_horaria_disponivel: int

@strawberry.type
class Query:
    @strawberry.field
    async def plano_trabalho(self, id: strawberry.ID) -> PlanoTrabalho:
        ...

schema = strawberry.Schema(query=Query, mutation=Mutation)
graphql_app = GraphQLRouter(schema)
```

| Critério | Avaliação |
|----------|-----------|
| DX / ergonomia | ⭐⭐⭐⭐⭐ — type hints Python diretos, sem duplicação |
| Type-safety | ⭐⭐⭐⭐⭐ — schema derivado dos tipos, impossível dessincronizar |
| Suporte a async | ⭐⭐⭐⭐⭐ — nativo |
| Integração FastAPI | ⭐⭐⭐⭐⭐ — `GraphQLRouter` drop-in |
| Dataloaders (N+1) | ⭐⭐⭐⭐ — suporte nativo (`strawberry.dataloader`) |
| Subscriptions (WebSocket) | ⭐⭐⭐⭐ — suporte nativo; útil para notificações em tempo real no dashboard |
| Exportação SDL | ⭐⭐⭐⭐⭐ — `strawberry export-schema` gera SDL para codegen de clientes |
| Codegen (TypeScript/Flutter) | ⭐⭐⭐⭐⭐ — SDL exportado é consumível por `graphql-codegen` e `artemis` |
| Maturidade | ⭐⭐⭐⭐ — v0.x, mas estável e muito ativo |
| Comunidade | ⭐⭐⭐ — menor que Graphene, crescendo |
| Documentação PT-BR | ⭐⭐ — majoritariamente em inglês |

**Vantagem principal:** eliminação da duplicação schema SDL ↔ código Python; menos surface de bugs. O SDL pode ser exportado com `strawberry export-schema app.main:schema > schema.graphql` e servir de contrato para clientes TypeScript (web) e Flutter/`artemis` (app móvel futuro).  
**Risco:** versão ainda abaixo de 1.0; breaking changes ocasionais.

---

### 2.2 Opção B — Ariadne + FastAPI

**Paradigma:** Schema-first (SDL separado do código Python)

```graphql
# schema.graphql
type PlanoTrabalho {
  id: ID!
  status: StatusPlanoTrabalhoEnum!
  cargaHorariaDisponivel: Int!
}

type Query {
  planoTrabalho(id: ID!): PlanoTrabalho
}
```

```python
# resolvers.py
from ariadne import QueryType
query = QueryType()

@query.field("planoTrabalho")
async def resolve_plano_trabalho(_, info, id: str):
    ...
```

| Critério | Avaliação |
|----------|-----------|
| DX / ergonomia | ⭐⭐⭐ — SDL e Python separados, mais verboso |
| Type-safety | ⭐⭐⭐ — necessário manter SDL e tipos Python sincronizados |
| Suporte a async | ⭐⭐⭐⭐⭐ — nativo |
| Integração FastAPI | ⭐⭐⭐⭐ — via ASGI handler |
| Dataloaders (N+1) | ⭐⭐⭐⭐ — suporte nativo |
| Subscriptions (WebSocket) | ⭐⭐⭐⭐ — suportado |
| Exportação SDL | ⭐⭐⭐⭐⭐ — SDL é o artefato primário; pronto para codegen |
| Codegen (TypeScript/Flutter) | ⭐⭐⭐⭐⭐ — SDL é a fonte de verdade; codegen de clientes direto |
| Maturidade | ⭐⭐⭐⭐⭐ — v0.24+, muito estável |
| Comunidade | ⭐⭐⭐⭐ — boa |
| Documentação PT-BR | ⭐⭐ — majoritariamente em inglês |

**Vantagem principal:** SDL legível por qualquer pessoa (útil se analistas de negócio precisam revisar o schema); facilita contratos com terceiros. SDL é a fonte de verdade para codegen de clientes TypeScript e Flutter.  
**Risco:** duplicação SDL ↔ Python; drift entre os dois se o time não for disciplinado.

---

### 2.3 Opção C — Graphene + FastAPI

**Paradigma:** Code-first (legado/clássico)

```python
import graphene

class PlanoTrabalho(graphene.ObjectType):
    id = graphene.ID()
    status = graphene.Int()
    carga_horaria_disponivel = graphene.Int()

class Query(graphene.ObjectType):
    plano_trabalho = graphene.Field(PlanoTrabalho, id=graphene.ID())

    def resolve_plano_trabalho(root, info, id):
        ...
```

| Critério | Avaliação |
|----------|-----------|
| DX / ergonomia | ⭐⭐ — muito verboso; classes, não type hints |
| Type-safety | ⭐⭐ — sem aproveitamento de type hints modernos |
| Suporte a async | ⭐⭐⭐ — suporte parcial; workarounds necessários |
| Integração FastAPI | ⭐⭐⭐ — possível, mais manual |
| Dataloaders (N+1) | ⭐⭐⭐ — via `graphene-django` ou manual |
| Subscriptions (WebSocket) | ⭐⭐ — suporte limitado; requer biblioteca adicional |
| Exportação SDL | ⭐⭐⭐ — possível via `graphene.Schema.graphql_schema.SDL`, menos ergonômico |
| Codegen (TypeScript/Flutter) | ⭐⭐⭐ — SDL exportável mas processo mais manual |
| Maturidade | ⭐⭐⭐⭐⭐ — v3+, muito estável, amplo ecossistema |
| Comunidade | ⭐⭐⭐⭐⭐ — maior |
| Documentação PT-BR | ⭐⭐⭐ — mais exemplos disponíveis |

**Vantagem principal:** maior base de exemplos e tutoriais; time já familiarizado com Django pode aproveitar.  
**Risco:** arquitetura async é um cidadão de segunda classe; verbosidade alta em domínios complexos como o PGD. **Descartado** pela combinação de suporte async deficiente + verbosidade excessiva.

---

### 2.4 Recomendação

> **Strawberry + FastAPI** (Opção A)

Justificativa: o domínio do PGD é rico em tipos e validações; Strawberry elimina a duplicação, aproveita ao máximo o type system do Python e tem suporte nativo a async (necessário para I/O com API PGD Central e banco de dados). O risco de ser sub-1.0 é aceitável dado o ritmo de releases e a adoção crescente.

**Alternativa segura:** se o time preferir uma biblioteca mais consolidada, Ariadne (Opção B) é a segunda escolha — madura, async-first, sem o peso do Graphene.

---

## 3. Stack Tecnológica Recomendada

| Camada | Tecnologia | Versão de referência | Justificativa |
|--------|-----------|----------------------|---------------|
| **Linguagem** | Python 3.12+ | 3.12 (api-pgd usa 3.11.4; subir para 3.12 no PGD Libre) | Requisito do projeto; 3.12 traz melhorias de desempenho |
| **GraphQL** | Strawberry (recomendado) ou Ariadne | strawberry-graphql ≥ 0.230 | Ver seção 2 |
| **HTTP Framework** | FastAPI | ≥ 0.111.0 (versão api-pgd) | Async-native, OpenAPI, maturidade |
| **ASGI Server** | Uvicorn | uvicorn[standard] ≥ 0.30.1 | Mesma versão da api-pgd; `[standard]` inclui websocket para subscriptions |
| **ORM** | SQLAlchemy 2.x (async) | ≥ 2.0.31 (versão api-pgd) | Expressividade, migrations via Alembic |
| **Driver PostgreSQL** | psycopg 3 (psycopg[binary]) | ≥ 3.2.1 (versão api-pgd) | **Importante:** api-pgd usa `psycopg` v3 (não `asyncpg` nem `psycopg2`); manter consistência |
| **Validação** | Pydantic v2 | pydantic[email] ≥ 2.8.2 (versão api-pgd) | Pydantic v2 é muito mais rápido; api-pgd já usa; necessário `[email]` para validar e-mails |
| **Banco de Dados** | PostgreSQL 16 | postgres:16 (versão docker-compose api-pgd) | api-pgd já usa PostgreSQL 16 no docker-compose; manter compatibilidade |
| **Tarefas agendadas** | Cloud Scheduler (GCP) + endpoint HTTP no próprio app | — | Endpoint interno `POST /internal/sync` protegido por header `X-Sync-Secret` é chamado pelo Cloud Scheduler em frequência configurável. Mesmo padrão para notificações e lembretes. Decisão tomada para evitar a complexidade operacional do Airflow/Cloud Composer (custo alto, curva de aprendizado, surface de manutenção) — o domínio não justifica DAGs complexos |
| **Autenticação** | authlib + Gov.br OIDC (prod) / Google OAuth (dev) | authlib ≥ 1.3 | Gov.br via OAuth2/OIDC (`https://sso.acesso.gov.br`); padrão do portal DGB; Google OAuth para desenvolvimento; authlib substitui python-jose — mais ativamente mantido e sem CVEs conhecidos |
| **Senha** | passlib + bcrypt | passlib ≥ 1.7.4, bcrypt ≥ 4.0.1 (versões api-pgd) | Mesmas versões da api-pgd |
| **HTTP Client** | httpx (async) | ≥ 0.27.0 (versão api-pgd) | Mesmo cliente da api-pgd; usado nos testes e no client da API Central |
| **Multipart** | python-multipart | ≥ 0.0.9 (versão api-pgd) | Necessário para OAuth2PasswordRequestForm no FastAPI |
| **Migrations** | Alembic | ≥ 1.13 | Padrão SQLAlchemy |
| **Containerização** | Docker + Docker Compose | Docker Compose v2 | Instalação simplificada no órgão; ver seção sobre Dockerfile |
| **Testes** | pytest + pytest-asyncio + httpx | pytest ≥ 8.2.2 (versão api-pgd) | Mesmas ferramentas da api-pgd |
| **Qualidade** | ruff (lint + format), mypy | ruff ≥ 0.4, mypy ≥ 1.10 | ruff substitui flake8 + isort + black |
| **Frontend Web** | SvelteKit | ≥ 2.0 | TypeScript-native SPA; graphql-codegen gera tipos e queries a partir do SDL exportado pelo Strawberry; ótima DX com SSR opcional |
| **Infraestrutura** | GCP (Cloud Run, Cloud SQL, Cloud Scheduler, Artifact Registry, Secret Manager) | — | Todos os ambientes (dev, testes, demos, produção) em GCP; Cloud Run para os serviços; Cloud SQL PostgreSQL 16; Cloud Scheduler para disparos periódicos dos endpoints internos; Secret Manager para credenciais |
| **IaC** | Terraform | ≥ 1.7 | Gerenciamento declarativo de toda a infraestrutura GCP; estado remoto no GCS; nunca rodar `apply` manualmente — somente via CI |
| **CI/CD** | GitHub Actions | — | Lint, testes, build de imagem, push para Artifact Registry e deploy no Cloud Run — tudo por workflow; ambientes separados por branch |
| **E-mail** | fastapi-mail | ≥ 1.4.1 (versão api-pgd) | Mesma biblioteca da api-pgd; notificações de avaliação, prazos |

> **Nota sobre o driver PostgreSQL:** A api-pgd usa `psycopg[binary]` v3 (não `asyncpg` nem `psycopg2`). Com SQLAlchemy 2.x async, a connection string deve ser `postgresql+psycopg://...` (não `postgresql+asyncpg://`). Manter esta escolha para consistência com o ecossistema de referência.

---

## 4. Estrutura de Pastas Proposta

```
pgd-libre/
├── docker-compose.yml          # Dev/produção simplificada (ver seção 4.1)
├── docker-compose.prod.yml     # Overrides de produção (sem --reload, sem portas expostas extras)
├── Dockerfile
├── .env.example                # Template de variáveis de ambiente (sem valores reais)
├── alembic/                    # Migrations
│   ├── env.py
│   └── versions/
├── src/
│   ├── main.py                 # Entry point FastAPI + GraphQL router + lifespan
│   ├── config.py               # Settings via pydantic-settings (lê de .env / env vars)
│   ├── db.py                   # Engine async, session factory, health check
│   │
│   ├── auth/                   # Autenticação e RBAC
│   │   ├── models.py           # SQLAlchemy: User
│   │   ├── schemas.py          # Pydantic: Token, UsersSchema
│   │   ├── crud.py             # create_user, authenticate_user, get_current_user
│   │   ├── resolvers.py        # GraphQL mutations: login, logout, changePassword
│   │   └── service.py          # JWT: create_access_token, verify_token
│   │
│   ├── domain/                 # Módulos de domínio (cada um com models/schemas/crud/service/resolvers)
│   │   ├── institucional/      # UnidadeAutorizadora, UnidadeInstituidora, UnidadeExecucao, AtoAutorizacao
│   │   ├── participante/       # Participante, TCR, Desligamento, Convocacao
│   │   ├── plano_entregas/     # PlanoEntregas, Entrega
│   │   ├── plano_trabalho/     # PlanoTrabalho, Contribuicao
│   │   ├── avaliacao/          # AvaliacaoRegistrosExecucao, Recurso, Compensacao
│   │   └── notificacao/        # E-mail, alertas de prazo (RF-029)
│   │
│   ├── integration/            # Integração com API PGD Central
│   │   ├── client.py           # HTTP client httpx async; auth POST /token
│   │   ├── mapper.py           # Local → contrato API Central (Participante, PE, PT)
│   │   └── sync.py             # Lógica de sincronização, retentativas, backoff exponencial
│   │
│   ├── api/                    # Endpoints HTTP não-GraphQL
│   │   └── sync.py             # POST /internal/sync (chamado pelo Cloud Scheduler;
│   │                           # protegido por header X-Sync-Secret)
│   │
│   ├── graphql/                # Schema GraphQL
│   │   ├── schema.py           # Composição do schema final (query + mutation + subscription)
│   │   ├── types/              # Tipos Strawberry por domínio
│   │   ├── scalars.py          # Scalars: CPF (validado), MatriculaSIAPE, Date
│   │   ├── permissions.py      # Classes IsAuthenticated, HasRole para RBAC nos resolvers
│   │   └── dataloaders.py      # DataLoaders para evitar N+1 (participantes, unidades)
│   │
│   ├── audit/                  # Auditoria transversal (RF-027)
│   │   ├── models.py           # SQLAlchemy: AuditLog (imutável)
│   │   └── middleware.py       # Captura automática de mudanças
│   │
│   └── jobs/                   # Lógica disparada pelos endpoints internos
│       ├── notify.py           # Notificações por e-mail (chamado por /internal/notify)
│       └── reminders.py        # Lembretes de prazo (chamado por /internal/reminders)
│
├── frontend/                   # Web UI
│   ├── templates/              # Jinja2 (health/redirect pages); app SvelteKit em repo separado
│   └── static/
│
├── docs/                       # Documentação operacional para TI do órgão
│   ├── instalacao.md
│   ├── variaveis-ambiente.md
│   └── backup-restore.md
│
└── tests/
    ├── conftest.py             # Fixtures: DB test, client httpx, factories
    ├── unit/
    ├── integration/            # Testes contra DB real (PostgreSQL em Docker)
    └── e2e/
```

### 4.1 Observações sobre Dockerfile e Docker Compose

A api-pgd de referência usa as seguintes escolhas que devem ser replicadas ou conscientemente divergidas:

| Aspecto | api-pgd (referência) | PGD Libre (recomendado) |
|---------|---------------------|------------------------|
| Imagem base | `python:3.11.4-slim-bullseye` | `python:3.12-slim-bookworm` (Debian mais recente) |
| Instalação de deps | `pip install --no-cache-dir` + limpeza apt | Igual; adicionar `--no-cache-dir` |
| Porta exposta | 5057 | 8000 (padrão FastAPI/uvicorn) ou configurável via env |
| `ENTRYPOINT` | `sh -c "cd /src && uvicorn ..."` | Manter mesmo padrão; usar `--workers` em prod |
| PostgreSQL (Compose) | `postgres:16` com healthcheck `pg_isready` | Igual — usar `postgres:16` |
| E-mail (Compose dev) | `smtp4dev` (servidor SMTP local) | Manter `smtp4dev` para desenvolvimento local |
| Volumes para dados | `./mnt/pgdata:/var/lib/postgresql/data` | Manter padrão; documentar política de backup |
| Variáveis sensíveis | Em texto claro no compose (aceitável para dev) | Separar em `.env` (nunca commitado); `.env.example` no repo |

**Diferença relevante:** o PGD Libre **não** usa background workers persistentes nem orquestrador (Airflow/Cloud Composer descartados pelo overhead operacional). A sincronização com a API Central e demais tarefas periódicas são expostas como endpoints HTTP internos protegidos por shared secret (`/internal/sync`, futuros `/internal/notify`, `/internal/reminders`). Em produção, o **Cloud Scheduler** chama esses endpoints em frequência configurável; em desenvolvimento local, basta `curl` ou agendamento via cron do sistema operacional.

```yaml
# Exemplo de variáveis de ambiente mínimas (docker-compose.yml)
environment:
  SQLALCHEMY_DATABASE_URL: postgresql+psycopg://postgres:postgres@db:5432/pgd_libre
  SECRET_KEY: <openssl rand -hex 32>
  ACCESS_TOKEN_EXPIRE_MINUTES: 30
  ALGORITHM: HS256
  API_PGD_URL: https://api.pgd.gov.br
  API_PGD_USERNAME: <email do sistema>
  API_PGD_PASSWORD: <senha do sistema>
  SYNC_SECRET: <openssl rand -hex 32>      # cabeçalho X-Sync-Secret validado em /internal/sync
  MAIL_SERVER: smtp4dev
  MAIL_PORT: 25
  MAIL_FROM: pgd@orgao.gov.br
```

---

## 5. Fases de Implementação

### Fase 0 — Fundação (2–3 semanas)

**Objetivo:** Base técnica funcionando; zero funcionalidade de negócio.

> **Dependência técnica crítica:** Todas as fases seguintes dependem desta fase estar completa. Não iniciar Sprint 1.1 antes de AuditLog e RBAC estarem funcionando — qualquer entidade criada depois precisará de auditoria e autorização desde o primeiro commit.

- [x] Repositório Git com estrutura de pastas (conforme seção 4)
- [x] `.env.example` com todas as variáveis documentadas; `.env` no `.gitignore`
- [x] Docker Compose: PostgreSQL 16 + smtp4dev + app
- [x] Dockerfile baseado em `python:3.12-slim-bookworm` com limpeza de cache apt (padrão api-pgd) — implementado em `Dockerfile` (non-root user, port 8000)
- [x] FastAPI bootstrapado com health check (`/health` inclui verificação de conexão com DB, padrão api-pgd) — **testes: `test_health.py`**
- [x] Middleware CSP nos endpoints `/docs` e `/redoc` (padrão api-pgd) — **teste: `test_csp.py`**
- [x] Middleware de verificação de `User-Agent` (padrão api-pgd — rejeita requisições sem cabeçalho) — **teste: `test_health_requires_user_agent`**
- [x] SQLAlchemy async configurado + Alembic; connection string `postgresql+psycopg://` (psycopg v3)
- [x] Autenticação OAuth2/OIDC via `authlib`: Google OAuth em dev, Gov.br (`https://sso.acesso.gov.br`) em produção — seguir padrão do portal DGB (`auth.ts`); variáveis de ambiente controlam qual provider está ativo — **testes: `test_auth_deps.py`, `test_auth_router.py`**
- [x] RBAC: permissões por papel implementadas nos resolvers GraphQL (`permissions.py`) — **testes: `test_permissions.py`**
- [x] Schema base do GraphQL (Strawberry): Query `health` + `me` funcionando via GraphiQL — **testes: `test_graphql.py`**
- [x] Modelos `User` e `AuditLog` com enums, defaults e constraints — **testes: `test_models.py`**
- [ ] **Repo `infra/` com Terraform e workflows GitOps** — repo novo em `/Users/nitai/dev/destaquesgovbr/pgd-libre/infra/`, coexistindo com `destaquesgovbr/infra` no mesmo projeto GCP `inspire-7-finep`. Prefixo `pgd-libre-` em todos os recursos. State em bucket exclusivo `pgd-libre-terraform-state`. Cloud SQL dedicado (`pgd-libre-postgres`). Reaproveita pool WIF existente `github-pool`.
- [x] Pipeline CI no repo `pgd-libre`: `.github/workflows/ci.yml` com ruff + mypy + pytest (service container PostgreSQL 16)

**Entregável:** Ambiente de desenvolvimento funcional. Endpoint `/health`, login/logout, schema GraphQL vazio mas navegável via GraphiQL. **Nenhum dado de negócio ainda.**

---

### Fase 1 — MVP — Ciclo Completo Local (8–10 semanas)

**Objetivo:** Um órgão consegue executar o ciclo completo do PGD no sistema, do cadastro à avaliação, sem integração com a API Central.

> **Dependência técnica:** Fase 0 completa é pré-requisito. A ordem das sprints abaixo reflete dependências de dados: não é possível criar PlanoTrabalho sem Participante com TCR ativo, e não é possível criar TCR sem UnidadeInstituidora configurada.

> **TDD:** cada item abaixo começa com o teste falhando. O arquivo de teste correspondente está indicado entre colchetes. Consultar `04-casos-de-teste.md` para o detalhamento de cada TC.

**Sprint 1.1 — Gestão Institucional (2 sem)** — `tests/test_institucional.py` (TC-M01)
- Cadastro de UnidadeAutorizadora e UnidadeInstituidora (RF-001, RF-002)
- Registro do ato de autorização e instituição com todos os campos do modelo
- Configuração de modalidades, vagas percentuais e conteúdo mínimo do TCR
- Gestão de usuários com RBAC (RF-025, RF-026) — criação, ativação, desativação, recuperação de senha
- Suspensão e revogação do PGD com notificação (RF-003) — implementar máquina de estados desde o início

> **Pré-condição para Sprint 1.2:** UnidadeAutorizadora e UnidadeInstituidora cadastradas.

**Sprint 1.2 — Participantes e TCR (2 sem)** — `tests/test_participante.py` (TC-M02)
- Cadastro de participantes com validação de CPF (dígitos verificadores) e matrícula SIAPE (RF-005)
- Verificação de elegibilidade: estágio probatório (1 ano), 6 meses após movimentação, limite 2% no exterior (RF-005, RF-006)
- Processo de seleção com critérios de prioridade quando vagas insuficientes (RF-006)
- Geração de minuta do TCR a partir dos parâmetros do ato de instituição + assinatura digital (RF-007)
- Desligamento com hipótese, justificativa e prazo de retorno (RF-008)
- Gestão de convocações presenciais com observância do prazo mínimo do TCR (RF-009)

> **Pré-condição para Sprint 1.3:** Participante com TCR ativo é pré-requisito para PlanoTrabalho (Sprint 1.4). A Sprint 1.3 pode correr em paralelo com 1.2 se o time tiver dois desenvolvedores independentes.

**Sprint 1.3 — Plano de Entregas (2 sem)** — `tests/test_plano_entregas.py` (TC-M03)
- CRUD do PlanoEntregas e Entregas com todos os campos do modelo (RF-010)
- Fluxo de aprovação pelo nível hierárquico superior (RF-011) — exceção para unidades instituidoras
- Máquina de estados completa: `Aprovado (2) → Em Execução (3) → Concluído (4) → Avaliado (5) / Cancelado (1)`
- Validação de sobreposição de períodos por unidade executora (regra api-pgd: rejeita com 422)
- Validação de duração máxima de 1 ano (regra api-pgd: validada na criação E na atualização pós cutoff)
- Ajustes durante execução com comunicação ao nível superior (RF-012)
- Avaliação do plano de entregas (escala 1–5) em até 30 dias após término (RF-013)

**Sprint 1.4 — Plano de Trabalho (2 sem)** — `tests/test_plano_trabalho.py` (TC-M04)
- CRUD do PlanoTrabalho e Contribuições com todos os campos do modelo (RF-014)
- Validação da soma de percentuais = 100% (salvo compensação)
- Tipos de contribuição (1, 2, 3) com regras específicas: tipo 1 exige `id_plano_entregas` + `id_entrega`; tipo 2 proíbe esses campos
- Validação: `data_inicio` do PT >= `data_inicio` do PE referenciado
- Validação de sobreposição de períodos por participante + unidade executora (regra api-pgd)
- Registro mensal de execução pelo participante (RF-015) — com prazo proporcional à duração do plano
- Máquina de estados: `Aprovado (2) → Em Execução (3) → Concluído (4) / Cancelado (1)`

**Sprint 1.5 — Avaliação e Recurso (1–2 sem)** — `tests/test_avaliacao.py` (TC-M04 avaliação + TC-M08)
- Avaliação de registros de execução pela chefia (escala 1–5; prazo 20 dias) (RF-017)
- Obrigatoriedade de justificativa para avaliações 1, 4 e 5
- Fluxo de recurso completo: participante recorre (10 dias) → chefia responde (10 dias) → decisão registrada (RF-018)
- Política de consequências: sinalização de ações de melhoria no TCR; pré-preenchimento de compensação no próximo plano (RF-019)
- Banco de horas: bloqueio de nova adesão; registro de saldo no TCR; prazo de 6 meses (RF-020)
- Relatórios de conformidade básicos (RF-028): participantes sem plano ativo, registros em atraso, avaliações pendentes

**Sprint 1.6 — Web UI básica + Auditoria + Notificações (1–2 sem)** — `tests/test_auditoria.py` (TC-M07), `tests/test_notificacoes.py` (TC-M08)
- Interface responsiva para os fluxos principais (priorizar: participante registra execução; chefia avalia; dashboard de prazos)
- Dashboard com prazos e alertas por papel
- Notificações por e-mail nos **8 eventos obrigatórios** do RF-029 (avaliação realizada, recurso, prazo iminente, convocação, desligamento, suspensão/revogação)
- Endpoint público de resultados consolidados por unidade (RF-004)

**Entregável:** Sistema instalável via `docker compose up`. Órgão consegue executar o ciclo completo do PGD.

**Critério de aceite do MVP:** Um participante real consegue criar plano de trabalho, registrar execução mensal, receber avaliação, recorrer, e a chefia consegue avaliar plano de entregas — tudo no sistema, com log de auditoria completo em cada operação.

---

### Fase 2 — Integração e Automação (4–6 semanas)

**Objetivo:** O sistema envia dados automaticamente à API PGD Central e o órgão tem visibilidade de conformidade.

> **Dependência técnica:** Fase 1 completa é pré-requisito. A Sprint 2.1 pode começar em paralelo com Sprint 1.6 se o mapper for desenvolvido independentemente da UI.

**Sprint 2.1 — Integração API PGD Central (2 sem)**
- HTTP client assíncrono httpx para a API PGD Central (autenticação via `POST /token` com `OAuth2PasswordRequestForm` — padrão da api-pgd)
- Mapper completo Local → contrato API Central para os três tipos de entidade (seção 4 do documento de modelo de dados)
- Tratamento especial: conversão de escala customizada → padrão antes do envio (RF-031)
- Envio manual sob demanda pelo administrador
- Tratamento diferenciado por código HTTP de resposta:
  - `200 OK` / `201 Created` → sucesso; atualiza `api_sincronizado_em`
  - `422 Unprocessable Entity` → erro de validação; registra em `RegistroEnvioAPI` com `resposta_body`; alerta administrador
  - `5xx` / timeout → retentativa com backoff exponencial (máx. 3 tentativas, delays: 1 min, 5 min, 30 min)
- Verificação de `User-Agent` obrigatório nas requisições à API Central (a api-pgd rejeita requisições sem esse header)

**Sprint 2.2 — Automação e Monitoramento (2 sem)**
- Endpoint interno `POST /internal/sync` protegido por header `X-Sync-Secret` (env var `SYNC_SECRET`); disparado periodicamente pelo **Cloud Scheduler** (RF-024)
- Lógica de coleta: participantes com situação/modalidade alterada + planos com status 3/4/5 e `api_sincronizado_em` desatualizado
- Backoff exponencial in-process (delays 1 min / 5 min / 30 min — ver `RETRY_DELAYS` em `src/integration/sync.py`); um erro num registo não interrompe os demais
- Painel de conformidade (GraphQL): total enviado com sucesso, total com erro (com detalhes), total pendente (RF-024)
- Reprocessamento manual de envios com falha via mutation `reprocessarEnvio`
- `RegistroEnvioAPI`: histórico completo com `tentativa`, `http_status`, `erro_mensagem`

**Sprint 2.3 — Escalas customizadas e Multi-tenant (1–2 sem)**
- Configuração de escala de avaliação própria com conversão automática para escala padrão 1–5 (RF-031)
- Suporte a múltiplas unidades autorizadoras na mesma instalação (RF-030)
- Isolamento de dados por `(origem_unidade, cod_unidade_autorizadora)` em todas as queries
- Testes de contrato contra a api-pgd real (ou seu docker-compose) para garantir compatibilidade do mapper

**Entregável:** Sistema totalmente conforme com a obrigação de envio de dados ao MGI.

---

### Fase 3 — Qualidade e Operação (3–4 semanas)

**Objetivo:** Sistema pronto para operação em produção com observabilidade, segurança e documentação.

**Segurança (OWASP Top 10 / RNF-003)**
- HTTPS forçado (redirect 301); cabeçalhos de segurança: CSP (padrão api-pgd), HSTS, X-Frame-Options
- Rate limiting nos endpoints de autenticação (`/token`, `/user/forgot_password`) para prevenir brute force
- Mascaramento de CPF em logs e respostas de erro (`123.***.**8-90` → não expor 11 dígitos em logs)
- Auditoria de dependências: `authlib` é a biblioteca de auth adotada; verificar CVEs ativos no CI com `pip-audit`
- Auditoria de dependências (`pip-audit` ou `safety`) integrada ao CI

**LGPD (RNF-007)**
- Política de retenção de dados: definir e documentar prazo de guarda de `AuditLog` e `RegistroEnvioAPI`
- Procedimento de anonimização para dados de participantes desligados (após prazo legal)
- Inventário de dados pessoais tratados: CPF, matrícula, e-mail, avaliações

**Observabilidade**
- Logs estruturados em JSON (formato `uvicorn.error` + campos extras: `user_id`, `unidade`, `operacao`)
- Métricas Prometheus: requests/s, latência p99, tamanho da fila de sincronização com API Central
- Alertas: fila de sincronização com > X itens pendentes; erro rate > Y%; DB connection failures

**Backup e Restore (lacuna crítica)**
- Documentar procedimento de backup do volume PostgreSQL (`pg_dump` agendado via cron no container ou externo)
- Testar restore: script `restore.sh` documentado em `docs/backup-restore.md`
- Estratégia: backup diário + retenção de 30 dias; backup antes de cada migration Alembic

**Documentação para TI do órgão**
- Guia de instalação: `docker compose up` + configuração de variáveis de ambiente
- Guia de atualização: procedimento de upgrade (pull nova imagem + `alembic upgrade head`)
- Guia de backup/restore
- Documentação de todas as variáveis de ambiente (com `.env.example` no repo)

**Testes e Performance**
- Testes de carga (k6 ou Locust): simular 50 usuários simultâneos no fluxo de registro mensal
- WCAG 2.1 AA no frontend (obrigatório para sistemas do governo federal — RNF-006)

---

## 6. Horizonte de Longo Prazo

### 6.1 Aplicativo Móvel

**Visão:** Aplicativo para servidores que permite registrar atividades, receber notificações de prazos, acompanhar o plano de trabalho e enviar registros de execução por áudio (transcrito por IA).

**Arquitetura:**
- O app consome a mesma API GraphQL do backend
- Autenticação via JWT (compartilhado com a web)
- Push notifications via FCM/APNs
- Notificações em tempo real via **GraphQL Subscriptions** (Strawberry suporta nativamente via WebSocket / `strawberry.subscription`); o cliente mobile subscreve a eventos como "nova avaliação disponível" ou "prazo se aproxima"
- **Codegen de clientes:** o SDL exportado (`strawberry export-schema`) alimenta o `graphql-codegen` (TypeScript) ou o `artemis` (Dart/Flutter), gerando tipos e queries tipadas automaticamente — elimina drift entre API e cliente
- Registro por áudio: Whisper (OpenAI/local) → transcrição → servidor registra descrição
- Stack: **Flutter** (cross-platform iOS/Android); `artemis` para codegen Dart a partir do SDL exportado pelo Strawberry

**Valor entregue:**
- Experiência drasticamente melhor para o servidor no dia a dia
- Registro mais frequente e próximo da execução real → dados mais precisos
- Notificações push eliminam o esquecimento de prazos (maior fonte de inadimplência)

**Dependências:** requer Fase 1 e 2 concluídas; API GraphQL estável; SDL exportado e versionado como artefato de build.

---

### 6.2 API PGD Central 2.0

**Visão:** Refatoração da API PGD Central do MGI, entregando uma versão mais moderna com:

- **Webhooks:** notificações push para os sistemas na ponta (ex.: "plano processado com sucesso", "inconsistência detectada"), eliminando a necessidade de polling
- **Endpoints de consulta avançada:** para os órgãos consultarem dados consolidados da rede PGD
- **Autenticação OAuth2 / API Key** em substituição ao modelo atual de usuário/senha
- **Versioning explícito:** `/v2/` com deprecação gerenciada de `/v1/`
- **Rate limiting e quotas** por órgão
- **Documentação OpenAPI 3.1** completa e atualizada automaticamente

**Valor entregue:**
- Elimina erros de integração por timeout/polling excessivo
- Melhora a confiabilidade do ecossistema como um todo
- Reduz carga operacional dos órgãos que integram

**Observação:** esta entrega requer aprovação e patrocínio do MGI; é uma proposta de melhoria da infraestrutura central, não apenas da ponta.

---

### 6.3 Analytics Central (Ministério da Gestão)

**Visão:** Plataforma de dados consolidados no MGI para análise do PGD em escala nacional.

**Componentes:**
- **Pipeline de ingestão:** Apache Airflow (Cloud Composer no GCP) recebendo dados de todos os órgãos via API Central — esse uso de Airflow é específico do agregador do MGI (volume e variedade de fontes justificam orquestrador). O PGD Libre na ponta de cada órgão **não** usa Airflow (ver seção 3).
- **Data Warehouse:** BigQuery ou PostgreSQL + dbt para transformações
- **Dashboards BI:** Superset ou Metabase para análises executivas (produtividade, distribuição de modalidades, adesão por órgão)
- **IA para gestores:** detecção de padrões (unidades sistematicamente com avaliação "inadequado", correlação entre modalidade e desempenho)
- **IA para servidores:** sugestão de metas, geração assistida de descrição de atividades, análise de carga horária

**Valor entregue:**
- O MGI passa de receptor passivo de dados para agente ativo de inteligência sobre o serviço público
- Subsídios para revisão de políticas de gestão de pessoas
- Transparência pública com dados consolidados da rede PGD

**Dependências:** requer API PGD Central 2.0 (dados estruturados e confiáveis); volume de dados significativo (mínimo ~50 órgãos ativos).

---

## 7. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|-------------|---------|-----------|
| Alteração do contrato da API PGD Central (nova IN) | Média | Alto | Manter mapper isolado; testes de contrato contra o docker-compose da api-pgd no CI |
| Órgão não tem infraestrutura para Docker | Média | Alto | Oferecer instalação em cloud (GCP Cloud Run como opção); documentar requisitos mínimos (2 vCPU, 4 GB RAM) |
| Resistência dos servidores em registrar atividades | Alta | Alto | UX simplificada, app móvel, registro por áudio |
| Dados pessoais (CPF) expostos em logs/erros | Baixa | Alto | Mascaramento automático em logs; nunca logar payload completo de participantes |
| API PGD Central indisponível no prazo de envio | Média | Médio | Fila com retentativa; painel de conformidade alerta; IN24 Art. 29 §único garante envio posterior |
| Complexidade do RBAC para hierarquias profundas | Média | Médio | Modelagem de papéis conservadora no MVP; expandir depois |
| Time desconhece Strawberry/GraphQL | Baixa | Médio | 1 semana de spike técnico na Fase 0 |
| Estágio probatório não é verificável automaticamente | Alta | Baixo | Campo declaratório no cadastro com aviso legal; chefia valida |
| Vulnerabilidades em biblioteca de auth | Baixa | Alto | `authlib` adotado — mais ativamente mantido que `python-jose`; `pip-audit` no CI detecta CVEs antes do deploy |
| Perda de dados por falta de backup documentado | Média | Alto | Implementar e testar procedimento de backup/restore na Fase 3 antes do go-live |
| Órgão precisa de LDAP/AD além do Gov.br | Baixa | Médio | authlib + OIDC suportam múltiplos providers; Keycloak como intermediário desacopla a app de qualquer IdP (ver seção 9) |
| `python-multipart` ausente causa falha silenciosa no login | Baixa | Alto | Já listado como dependência obrigatória; verificar no requirements.txt antes do deploy |

---

## 8. Estimativa de Esforço por Fase

> Estimativa de referência para **1 desenvolvedor sênior + 1 desenvolvedor pleno**. Ajustar conforme composição real da equipe.

| Fase | Duração estimada | Esforço total |
|------|----------------|---------------|
| Fase 0 — Fundação | 2–3 semanas | ~3 pessoas-semana |
| Fase 1 — MVP | 8–10 semanas | ~16 pessoas-semana |
| Fase 2 — Integração | 4–6 semanas | ~8 pessoas-semana |
| Fase 3 — Produção | 3–4 semanas | ~6 pessoas-semana |
| **Total plataforma na ponta** | **~17–23 semanas** | **~33 pessoas-semana** |

Horizontes futuros (estimativas de alto nível):

| Horizonte | Esforço estimado |
|-----------|-----------------|
| App Móvel (MVP) | ~16 pessoas-semana |
| API PGD Central 2.0 | ~20 pessoas-semana (requer negociação com MGI) |
| Analytics Central (MVP) | ~24 pessoas-semana |

---

## 9. Decisões Fechadas e Decisões em Aberto

### Decisões fechadas

| Decisão | Escolha |
|---------|---------|
| Stack GraphQL | **Strawberry + FastAPI** (ver seção 2) |
| Frontend Web | **SvelteKit** |
| Tarefas agendadas | **Cloud Scheduler** chamando endpoints HTTP internos (`/internal/sync`, etc.) protegidos por `X-Sync-Secret`. Sem orquestrador/worker persistente — Airflow descartado |
| App Móvel stack | **Flutter** (`artemis` para codegen Dart) |
| Modelo de instalação | **Self-hosted** (Docker Compose por órgão) |
| Autenticação federada | **Gov.br OIDC** em produção + Google OAuth em dev (padrão do portal DGB) |
| Biblioteca OAuth/JWT | **authlib ≥ 1.3** (substitui python-jose — melhor manutenção, sem CVEs conhecidos) |
| Infraestrutura | **GCP** (Cloud Run, Cloud SQL, Cloud Scheduler, Artifact Registry, Secret Manager) |
| IaC | **Terraform** (estado remoto no GCS; apply só via CI) |
| CI/CD | **GitHub Actions** |
| AuditLog | **Chamadas explícitas pelos services** (38 call sites em `src/services/*.py`). Listener SQLAlchemy automático foi descartado: perde contexto semântico (ação específica como APROVAR vs REJEITAR — ambos seriam UPDATE), perde `user`/`ip_address`/`old_values` capturados antes de mutações, e dificulta capturar estado anterior em operações complexas |
| Convenção de nomes GCP | **Prefixo `pgd-libre-`** em todos os recursos (Cloud Run, Cloud SQL, Secret Manager, Artifact Registry, Cloud Scheduler, service accounts). Coexistência com Destaques Gov BR (`destaquesgovbr-*`) no mesmo projeto `inspire-7-finep`. Terraform state em bucket exclusivo `pgd-libre-terraform-state`. Cloud SQL dedicado (`pgd-libre-postgres`, PostgreSQL 16). Reaproveita pool WIF `github-pool` já existente no projeto |

### Decisões ainda em aberto

| Decisão | Opções | Critério de escolha |
|---------|--------|-------------------|
| **Versão do SDL como artefato** | SDL gerado em CI e publicado no release vs apenas em desenvolvimento local | Necessário se o app mobile for desenvolvido por equipe separada; versionamento garante compatibilidade entre releases |
| **Estratégia de testes de contrato** | pact-python vs rodar docker-compose da api-pgd no CI | docker-compose da api-pgd no CI é mais simples e garante teste real contra a implementação de referência |
| **Política de backup no órgão** | Backups automatizados nativos do Cloud SQL vs `pg_dump` agendado vs WAL archiving (pgbackrest/Barman) | Cloud SQL já oferece backups automáticos e PITR; suficiente para a maioria dos órgãos. `pg_dump` adicional para portabilidade entre instalações; WAL archiving para RPO < 1h em órgãos de alta criticidade |
| **Caminho Gov.br → Keycloak** | OIDC direto no Gov.br vs via instância Keycloak própria | Keycloak desacopla a app do provider externo e facilita LDAP/AD paralelo; decisão impacta arquitetura de auth antes da Fase 0 |

---

## 10. Próximos Passos Imediatos

1. **Decidir Gov.br direto vs Keycloak** — única decisão de auth ainda em aberto; impacta a arquitetura desde a Fase 0 (ver seção 9)
2. **Spike técnico** de 1 semana: criar protótipo com Strawberry + FastAPI + SQLAlchemy async (psycopg v3) com 2 resolvers de domínio do PGD; autenticação com authlib (Google OAuth em dev); exportar SDL; gerar tipos TypeScript com graphql-codegen
3. **Setup GCP/Terraform/GitHub Actions:** criar projeto GCP, habilitar APIs (Cloud Run, Cloud SQL, Cloud Scheduler, Artifact Registry, Secret Manager), Terraform para infra base, workflows de CI/CD mínimos (lint + testes + build + deploy)
4. **Registrar client_id Gov.br** na plataforma de homologação do MGI (acesso.gov.br) para ter credenciais antes de iniciar a Fase 1
5. **Revisar e priorizar RFs** do documento `01-requisitos-funcionais.md` com stakeholders para confirmar escopo do MVP
6. **Criar repositório** `pgd-libre/app` com estrutura de pastas da seção 4, incluindo `.env.example`
7. **Iniciar Fase 0** com foco em CI/CD e infraestrutura antes de qualquer código de negócio

---

## 11. Notas da Revisão

**Versão:** 0.6 — 2026-05-14  
**Revisor:** Decisões tecnológicas confirmadas pelo responsável do projeto

### Alterações v0.6 — 2026-05-14

**Fechamento da Fase 0.** Cinco decisões tomadas após auditoria do que ainda estava
não-marcado no checklist:

1. **Dockerfile** — marcado como feito (`[x]`). O arquivo já existia em `Dockerfile`
   com o padrão exato pedido (`python:3.12-slim-bookworm`, non-root, port 8000); só
   faltava marcar.

2. **Recuperação de senha removida do checklist.** A v0.3 fechou Gov.br OIDC + Google
   OAuth, e o modelo `User` não tem `password_hash` — só `oauth_sub`/`oauth_provider`.
   O item ficou obsoleto e foi removido (não há recuperação de senha local a fazer).

3. **Spike técnico removido do checklist.** As Sprints 1.1–2.8 (304 testes verdes)
   já validaram retroativamente a stack Strawberry + FastAPI + SQLAlchemy async +
   psycopg v3. Spike formal perdeu propósito.

4. **AuditLog automático descartado** — promovido a decisão fechada na seção 9.
   O pattern manual (38 call sites em `src/services/*.py`) carrega contexto
   semântico (ação específica, `user`, `ip_address`, `old_values`) que um listener
   SQLAlchemy automático perderia.

5. **Estrutura de IaC redesenhada.** O item genérico "GCP/CI setup" foi
   reescrito como dois itens distintos: (a) repo `infra/` em
   `/Users/nitai/dev/destaquesgovbr/pgd-libre/infra/`, coexistindo lado a lado
   com o `destaquesgovbr/infra` no mesmo projeto GCP `inspire-7-finep` via
   prefixo `pgd-libre-` em todos os recursos, com state em bucket exclusivo
   `pgd-libre-terraform-state` e Cloud SQL dedicado `pgd-libre-postgres`;
   (b) pipeline CI no próprio repo `pgd-libre/.github/workflows/ci.yml`
   (lint + mypy + pytest com Postgres 16 service container). A convenção de
   nomes virou decisão fechada (seção 9).

Plano executivo de fechamento em `_plan/fase-0-conclusao.md`.

### Alterações v0.5 — 2026-05-14

**Apache Airflow descartado — substituído por Cloud Scheduler + endpoint HTTP.**

Após reavaliação do overhead operacional do Airflow/Cloud Composer (custo mínimo de
~US$ 400/mês, curva de aprendizado, surface de patches/upgrades, complexidade de
deploy de DAGs) versus a simplicidade do domínio (uma sincronização periódica com
retry/backoff in-process, sem dependências entre tarefas, sem fan-out), a equipe
optou por uma abordagem mais leve:

- **Endpoint interno** `POST /internal/sync` protegido por header `X-Sync-Secret`
  (env var `SYNC_SECRET`) já implementado em `src/api/sync.py`
- **Cloud Scheduler** chama esse endpoint na frequência desejada (ex.: diário às 03h)
- Retry/backoff exponencial é responsabilidade do próprio service de sincronização
  (delays 1 min / 5 min / 30 min — ver `RETRY_DELAYS` em `src/integration/sync.py`)
- Mesmo padrão será usado para notificações por e-mail e lembretes de prazo

**Trade-offs:**
- ✅ Operação trivial: sem orquestrador para manter, sem DAGs para deployar
- ✅ Stack 100% Python — sem Airflow runtime separado
- ✅ Custo Cloud Scheduler é desprezível (3 jobs grátis/mês, depois ~US$ 0.10/job/mês)
- ❌ Sem UI de monitoramento gráfico estilo Airflow — substituído pelo painel
  GraphQL `painelConformidade` + tabela `RegistroEnvioAPI` (já implementados)
- ❌ Sem retries de infra-nível: se o app cair, o Scheduler não tem fila persistente.
  Mitigação: Cloud Scheduler tem retry configurável próprio (até 5 tentativas com
  backoff exponencial nativo), e o próximo disparo periódico recupera entidades
  ainda não sincronizadas (`api_sincronizado_em IS NULL`).

**Seções afetadas:** 1.3 (separação de responsabilidades), 3 (stack), 4 (estrutura
de pastas — `airflow_dags/` removida, `src/api/` adicionada), 4.1 (Docker Compose),
5.2.2 (Sprint 2.2), 6.3 (nota: Airflow continua relevante para o agregador do MGI,
mas não para a ponta), 9 (decisões fechadas), 10 (próximos passos).

### v0.4 e anteriores: o que foi alterado e por quê

**Seção 2 — Comparativo de stacks GraphQL**

- **Adicionadas linhas de critério** nas tabelas de comparação das três opções: "Subscriptions (WebSocket)", "Exportação SDL" e "Codegen (TypeScript/Flutter)". Strawberry e Ariadne têm suporte nativo a subscriptions — relevante para notificações em tempo real no dashboard e no app móvel futuro. A capacidade de exportar SDL é crítica para o roadmap de app móvel: o comando `strawberry export-schema` gera o SDL que alimenta `graphql-codegen` (TypeScript) e `artemis` (Dart/Flutter).
- **Graphene:** adicionada nota explícita de descarte justificado pela combinação de suporte async deficiente e verbosidade, para que não reste dúvida na leitura.

**Seção 3 — Stack tecnológica**

- **Versões explicitadas** para todas as bibliotecas, baseadas no `requirements.txt` da api-pgd de referência. Versões pinadas: FastAPI 0.111.0, SQLAlchemy 2.0.31, psycopg[binary] 3.2.1, pydantic[email] 2.8.2, python-jose[cryptography] 3.3.0, passlib 1.7.4, bcrypt 4.0.1, httpx 0.27.0, fastapi-mail 1.4.1, pytest 8.2.2.
- **Driver PostgreSQL clarificado:** a api-pgd usa `psycopg` v3 (não `asyncpg` nem `psycopg2`); a connection string com SQLAlchemy async deve usar `postgresql+psycopg://`. Esta é uma diferença técnica silenciosa que causaria falha se o time assumisse `asyncpg`.
- **PostgreSQL 16** especificado (versão do `docker-compose.yml` da api-pgd, não 15+ genérico).
- **Uvicorn com `[standard]`** especificado — necessário para suporte a WebSocket (subscriptions GraphQL).
- **Alerta sobre `python-jose`** com CVEs potenciais; alternativa `authlib` documentada.

**Seção 4 — Estrutura de pastas**

- **Módulo `audit/`** extraído para módulo próprio (era só citado no texto). AuditLog é transversal a todos os módulos e merece isolamento claro.
- **`graphql/permissions.py`** e **`graphql/dataloaders.py`** adicionados explicitamente — são componentes que surgem cedo e precisam de home definida.
- **`docker-compose.prod.yml`** adicionado para separar overrides de produção (sem `--reload`, sem portas extras).
- **`.env.example`** adicionado à raiz — prática obrigatória para segurança; `.env` não deve ser commitado.
- **`docs/`** adicionado para documentação operacional (instalação, variáveis, backup).
- **Seção 4.1 adicionada:** tabela comparativa entre o Dockerfile/docker-compose da api-pgd e o recomendado para o PGD Libre. Inclui alinhamentos (postgres:16, smtp4dev, limpeza apt) e divergências conscientes (python 3.12, porta 8000, `.env` separado). Documenta variáveis de ambiente mínimas necessárias.

**Seção 5 — Fases de implementação**

- **Fase 0:** adicionado aviso sobre dependência técnica crítica (AuditLog e RBAC antes de qualquer entidade de negócio). Adicionados: middleware CSP e User-Agent (padrão api-pgd), spike técnico de 1 semana como item explícito, recuperação de senha, `python:3.12-slim-bookworm` como imagem base.
- **Fase 1:** dependências técnicas entre sprints tornadas explícitas (ex.: TCR ativo é pré-condição para PlanoTrabalho). Adicionadas regras técnicas específicas identificadas no código da api-pgd: validação de sobreposição de períodos com 422, validação de 1 ano com cutoff date para updates, verificação de `data_inicio` do PT >= `data_inicio` do PE, tipo 2 proíbe `id_plano_entregas`. Avaliações 1, 4 e 5 com justificativa obrigatória explicitadas.
- **Fase 2:** autenticação com a API Central detalhada (OAuth2PasswordRequestForm, padrão da api-pgd). Adicionado: verificação de `User-Agent` obrigatório nas requisições. Delays específicos de backoff (1 min, 5 min, 30 min). Testes de contrato contra o docker-compose da api-pgd sugeridos.
- **Fase 3 (expandida):** seção de backup/restore adicionada como **lacuna crítica** — o plano original não mencionava estratégia de backup. Adicionadas: política de retenção LGPD, inventário de dados pessoais, auditoria de dependências no CI, alerta sobre `python-jose`.

**Seção 6 — Horizontes futuros**

- **App móvel:** adicionados detalhes sobre GraphQL Subscriptions (Strawberry suporte nativo via WebSocket) para notificações em tempo real. Adicionado codegen de clientes como dependência técnica do desenvolvimento mobile. SDL exportado deve ser artefato versionado de build.

**Seção 7 — Riscos**

- Adicionados 4 riscos novos: vulnerabilidades em `python-jose`, perda de dados por falta de backup, necessidade de SSO/login federado (Gov.br/LDAP — comum em órgãos federais), ausência de `python-multipart` como falha silenciosa no login.

**Seção 9 — Decisões em aberto**

- Adicionadas 5 novas decisões: autenticação federada SSO (Gov.br/LDAP/SAML), JWT library (python-jose vs authlib), SDL como artefato versionado, estratégia de testes de contrato (docker-compose da api-pgd vs pact), política de backup.

**Seção 10 — Próximos passos**

- Adicionado item sobre decisão de autenticação federada como pré-requisito da Fase 0. Adicionada decisão sobre APScheduler vs Celery como impactante para o `docker-compose.yml` desde o início.

---

### Alterações v0.4 — 2026-05-13

**Metodologia TDD adicionada (seção 1.4)**

- Mandato TDD formal: Red → Green → Refactor para todo código novo.
- Documentada a estrutura de arquivos de teste (`tests/test_*.py` por módulo/sprint).
- Fase 0 atualizada com checkboxes marcados para o que já foi implementado e testado.
- Cada sprint da Fase 1 agora referencia o arquivo de teste e os TCs correspondentes.
- **Bug corrigido em `src/auth/router.py`:** `oauth.create_client()` retorna `None` (não `RuntimeError`) para providers não registrados; a guarda foi trocada de `try/except RuntimeError` para `if client is None`.
- 54 testes passando em `tests/` cobrindo: JWT, `get_optional_user`, endpoints `/auth/*`, query GraphQL `me`, classes de permissão e constraints dos modelos.

### Alterações v0.3 — 2026-05-13

**Decisões tecnológicas fechadas pelo responsável do projeto:**

- **Background jobs:** substituído Celery + Redis por **Apache Airflow** (Cloud Composer no GCP). Responsável tem larga experiência com Airflow; Cloud Composer elimina operação manual do scheduler em ambiente GCP.
- **Autenticação:** substituído `python-jose` por **authlib ≥ 1.3**; provider de produção é **Gov.br OIDC** (`https://sso.acesso.gov.br`), Google OAuth em desenvolvimento — padrão idêntico ao portal DGB já implantado.
- **Frontend:** confirmado **SvelteKit** como única opção (removida alternativa HTMX).
- **App móvel:** confirmado **Flutter** (removida alternativa React Native); `artemis` para codegen Dart.
- **Modelo de instalação:** confirmado **self-hosted** (Docker Compose por órgão).
- **Infraestrutura:** todos os ambientes em **GCP**; **Terraform** para IaC; **GitHub Actions** para CI/CD.
- **Migração de dados:** fora do escopo por ora.

**Seção 3 — Stack tecnológica:** adicionadas linhas para Infraestrutura (GCP), IaC (Terraform) e CI/CD (GitHub Actions). Removida linha de Redis.

**Seção 5 — Fase 0:** substituída referência a Redis/Celery por item de setup GCP/CI/CD; autenticação reescrita para Gov.br OIDC + authlib seguindo padrão DGB.

**Seção 9 — Decisões em aberto:** tabela dividida em "Fechadas" e "Em aberto". Fechadas: Strawberry, SvelteKit, Airflow, Flutter, self-hosted, Gov.br, authlib, GCP, Terraform, GitHub Actions. Mantidas em aberto: Gov.br direto vs Keycloak, SDL como artefato, testes de contrato, backup.

**Seção 10 — Próximos passos:** atualizado para refletir as decisões fechadas; adicionado item de registro do client_id Gov.br e setup GCP.
