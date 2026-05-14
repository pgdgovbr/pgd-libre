#!/usr/bin/env bash
# Entrypoint do container do PGD Libre.
# Roda migrations Alembic antes de subir o uvicorn — assim cada deploy
# garante schema atualizado.
set -euo pipefail

echo "[entrypoint] alembic upgrade head"
alembic upgrade head

echo "[entrypoint] starting uvicorn on :${PORT:-8000}"
exec uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}"
