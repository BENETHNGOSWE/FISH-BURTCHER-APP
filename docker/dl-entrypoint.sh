#!/usr/bin/env bash
set -e

BENCH=/home/frappe/frappe-bench

if [ -d "$BENCH/sites" ]; then
  ls -1 "$BENCH/apps" > "$BENCH/sites/apps.txt" 2>/dev/null || true
fi

exec /usr/local/bin/entrypoint.sh "$@"
