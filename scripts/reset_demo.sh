#!/bin/bash
# reset_demo.sh — Daily demo data reset for PGD Libre
#
# Usage:
#   # Run directly inside container:
#   docker exec pgd-libre-app-1 bash scripts/reset_demo.sh
#
#   # Schedule via host crontab (runs at 03:00 AM daily):
#   0 3 * * * docker exec pgd-libre-app-1 python scripts/seed_demo.py >> /tmp/pgd-seed.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${LOG_FILE:-/tmp/pgd-seed.log}"
TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"

echo "[$TIMESTAMP] Iniciando reset de dados demo..." | tee -a "$LOG_FILE"

python "$SCRIPT_DIR/seed_demo.py" 2>&1 | tee -a "$LOG_FILE"

echo "[$TIMESTAMP] Reset concluído." | tee -a "$LOG_FILE"
