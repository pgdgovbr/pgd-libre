# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup — always use Python 3.12
python3.12 -m venv .venv
source .venv/bin/activate
PIP_NO_INPUT=1 pip install -r requirements-dev.txt   # bypasses private GCP Artifact Registry prompt

# Run dev server
uvicorn src.main:app --reload

# Tests
pytest                           # all tests
pytest tests/test_health.py      # single file
pytest -k "test_health"          # single test by name

# Lint / format / types
ruff check src tests
ruff check --fix src tests
ruff format src tests
mypy src

# Alembic
alembic upgrade head
alembic revision --autogenerate -m "description"
```

## Architecture

### Request flow

```
HTTP → SessionMiddleware (OAuth CSRF state) → CORSMiddleware → UserAgent guard
    → /auth/*    FastAPI router  (OAuth2 code flow, JWT cookie)
    → /graphql   Strawberry GraphQLRouter (context_getter injects db + user)
    → /healthz   plain router
```

### Auth

`src/auth/oauth.py` builds an `authlib` `OAuth` object at module load time. Providers are registered **only if the corresponding env var is set** (`GOOGLE_CLIENT_ID`, `GOVBR_CLIENT_ID`). This means the app starts with no OAuth providers when env vars are absent — same pattern as the DGB portal's NextAuth.js `auth.ts`.

`src/auth/deps.py` issues and validates JWTs with **PyJWT** (not `authlib.jose`, which is deprecated in authlib ≥ 1.7). Tokens are stored as `httpOnly` cookies (`access_token`, `SameSite=Lax`, `Secure` only in production).

`get_optional_user` is a FastAPI dependency that reads the cookie and returns `User | None`. It is injected into the GraphQL context via `get_context` in `src/graphql/schema.py`.

### GraphQL

Strawberry is configured with `context_getter=get_context`, which injects `{request, db, user}`. Permission classes in `src/graphql/permissions.py` read `info.context.get("user")`. Adding new mutations/queries: define the resolver in a separate file, add to the root `Query`/`Mutation` type in `schema.py`, guard with a permission class using `@strawberry.field(permission_classes=[...])`.

### Database

Driver is **psycopg v3** (`postgresql+psycopg://`), not asyncpg. `NullPool` is used so the app works correctly in Cloud Run's process-per-request model.

**Critical**: use Python-side `default=` for enum columns, not `server_default=`. PostgreSQL does not know about SQLAlchemy's enum type until after the first `CREATE TYPE` transaction commits; `server_default` triggers `invalid input value for enum` errors.

### Migrations

`alembic/env.py` uses the async pattern: `async_engine_from_config` + `connection.run_sync(do_run_migrations)`. Alembic reads `DATABASE_URL` from `get_settings()`. Each migration file must handle both enum type creation and table creation in the correct order.

### RBAC

`UserRole` enum (in `src/models/user.py`): `admin > gestor_unidade > chefe_imediato > servidor`. Permission classes implement the hierarchy — `IsChefiaOrAbove` includes all three top roles.

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | `postgresql+psycopg://user:pass@host/db` |
| `SECRET_KEY` | yes | JWT signing + session middleware |
| `FRONTEND_URL` | yes | Redirect target after OAuth callback |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | no | Activates Google OAuth provider |
| `GOVBR_CLIENT_ID` / `GOVBR_CLIENT_SECRET` | no | Activates Gov.br OIDC provider |

## pip.conf gotcha

The global pip.conf at `~/.config/pip/pip.conf` has an `extra-index-url` pointing to a private GCP Artifact Registry. This blocks non-interactive installs with an EOF error. Always use `PIP_NO_INPUT=1` when installing.
