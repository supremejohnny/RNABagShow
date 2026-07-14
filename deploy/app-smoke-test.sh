#!/usr/bin/env bash

set -euo pipefail

APP_PORT="${RNABAG_APP_PORT:-8000}"
BASE_URL="http://127.0.0.1:$APP_PORT"

curl --fail --silent --show-error "$BASE_URL/api/v1/health/live"
echo
curl --fail --silent --show-error "$BASE_URL/api/v1/health/ready"
echo
curl --fail --silent --show-error "$BASE_URL/api/v1/tasks" >/dev/null
curl --fail --silent --show-error "$BASE_URL/" >/dev/null

echo "RNABag web and API smoke checks passed at $BASE_URL/"
