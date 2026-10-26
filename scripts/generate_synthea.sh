#!/usr/bin/env bash
# Pinned upstream release, fixed seeds/dates, UTC, and one generation thread.
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output="${1:-$project_root/data/synthea}"
population="${2:-10}"
if [[ ! "$population" =~ ^[1-9][0-9]*$ ]]; then
  echo 'Population must be a positive integer' >&2
  exit 1
fi
if [[ -e "$output" ]]; then
  echo "Refusing to overwrite existing output: $output" >&2
  exit 1
fi
mkdir -p "$project_root/data/tools"
jar="$project_root/data/tools/synthea-v3.3.0.jar"
expected='8ba04f7d73abadd5a377e41edf24c5c83935a1cb07c6d982cd5db731ef1cf445'
if [[ ! -f "$jar" ]]; then
  curl --fail --location --silent --show-error \
    https://github.com/synthetichealth/synthea/releases/download/v3.3.0/synthea-with-dependencies.jar \
    -o "$jar"
fi
printf '%s  %s\n' "$expected" "$jar" | sha256sum --check --status
mkdir -p "$output"
output="$(cd "$output" && pwd)"
java -Duser.timezone=UTC -Duser.language=en -Duser.country=US -jar "$jar" \
  -s 42 -cs 42 -r 20240101 -e 20250101 -p "$population" Florida \
  --generate.thread_pool_size=1 \
  --exporter.csv.export=true --exporter.csv.append_mode=false \
  --exporter.csv.folder_per_run=false --exporter.years_of_history=0 \
  --exporter.fhir.export=false --exporter.hospital.fhir.export=false \
  --exporter.practitioner.fhir.export=false --exporter.baseDirectory="$output"
printf 'CSV exports: %s/csv\n' "$output"
