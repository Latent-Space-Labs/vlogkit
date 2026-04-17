#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

SNAPSHOT="tests/server/snapshots/openapi.json"
if [[ ! -f "$SNAPSHOT" ]]; then
  echo "Missing $SNAPSHOT — run tests first to generate it." >&2
  exit 1
fi

OUT="desktop/web/src/lib/api-types.ts"
echo "Generating $OUT from $SNAPSHOT..."
npx --prefix desktop/web openapi-typescript "$SNAPSHOT" -o "$OUT"
echo "Done."
