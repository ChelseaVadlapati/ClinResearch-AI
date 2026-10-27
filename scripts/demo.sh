#!/usr/bin/env bash
# Reversible synthetic-only source-mounted demo; never delete volumes or prior runs.
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
if [[ ! -f .env ]]; then
  python3 scripts/init_env.py
fi
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-clinresearch-portfolio}"
export POSTGRES_PORT="${POSTGRES_PORT:-15432}"
export API_PORT="${API_PORT:-18000}"
export DASHBOARD_PORT="${DASHBOARD_PORT:-18501}"
export API_BASE_URL="http://localhost:$API_PORT"
export DASHBOARD_BASE_URL="http://localhost:$DASHBOARD_PORT"
export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml:docker-compose.ci.yml}"
run_id="$(python3 -c 'from uuid import uuid4; print(uuid4().hex)')"
export INGEST_REPORT_PATH="/app/reports/demo-$run_id/ingest.json"
export RESEARCH_REPORT_PATH="/app/reports/demo-$run_id/research/report.json"
export NLP_REPORT_PATH="/app/reports/demo-$run_id/nlp/report.json"
if [[ -n "${DEMO_CA_BUNDLE:-}" ]]; then
  ca_override="$(mktemp /tmp/clinresearch-demo-ca.XXXXXX.yml)"
  trap 'rm -f "$ca_override"' EXIT
  cat > "$ca_override" <<'EOF'
services:
  deps:
    environment:
      PIP_CERT: /run/demo-ca.pem
    volumes:
      - ${DEMO_CA_BUNDLE}:/run/demo-ca.pem:ro
EOF
  export COMPOSE_FILE="$COMPOSE_FILE:$ca_override"
fi
docker compose up --no-build -d --wait --wait-timeout 300
python3 scripts/smoke_demo.py
# Fresh per-run output directories; no previous artifact is replaced.
docker compose run --rm --no-deps ingest python -m clinresearch.cli analyze \
  --observation-end 2025-01-01 --split-date 2024-01-01 \
  --config configs/adult-return-v1.json --output "/app/reports/demo-$run_id/research"
docker compose run --rm --no-deps ingest python -m clinresearch.nlp.benchmark \
  --output "/app/reports/demo-$run_id/nlp"
python3 scripts/smoke_research.py
python3 scripts/smoke_explore.py
printf '\nSynthetic-only demo: %s\nAPI: %s/docs\nArtifacts: reports/demo-%s\n' \
  "$DASHBOARD_BASE_URL" "$API_BASE_URL" "$run_id"
printf 'Transformer is not run by this lightweight demo; use docs/nlp-evaluation.md for that experiment.\n'
