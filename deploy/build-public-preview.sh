#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="${1:-}"

if [[ -z "$OUTPUT_DIR" || "$OUTPUT_DIR" != /* ]]; then
  echo "Usage: $0 /absolute/empty/output-directory" >&2
  exit 2
fi
if [[ -e "$OUTPUT_DIR" && ! -d "$OUTPUT_DIR" ]]; then
  echo "Output path exists and is not a directory: $OUTPUT_DIR" >&2
  exit 1
fi
if [[ -d "$OUTPUT_DIR" ]] && [[ -n "$(find "$OUTPUT_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "Output directory must be empty: $OUTPUT_DIR" >&2
  exit 1
fi

install -d -m 0755 "$OUTPUT_DIR/frontend" "$OUTPUT_DIR/asset"
install -m 0644 "$PROJECT_ROOT/index.html" "$OUTPUT_DIR/index.html"
install -m 0644 "$PROJECT_ROOT/frontend/index.html" "$OUTPUT_DIR/frontend/index.html"
install -m 0644 "$PROJECT_ROOT/frontend/ranbag_lab.html" "$OUTPUT_DIR/frontend/ranbag_lab.html"
install -m 0644 "$PROJECT_ROOT/frontend/rnabag-variant.js" "$OUTPUT_DIR/frontend/rnabag-variant.js"
install -m 0644 "$SCRIPT_DIR/public-preview/rnabag-runtime-config.js" "$OUTPUT_DIR/frontend/rnabag-runtime-config.js"
install -m 0644 "$PROJECT_ROOT/asset/overview.png" "$OUTPUT_DIR/asset/overview.png"

if find "$OUTPUT_DIR" -type f \( -name '*.tsv' -o -name '*.pt' -o -name '*.pth' -o -name '*.py' -o -name '*.env' \) -print | grep -q .; then
  echo "Public preview contains a forbidden data, model, code, or config file." >&2
  exit 1
fi

echo "Public preview built at $OUTPUT_DIR"
