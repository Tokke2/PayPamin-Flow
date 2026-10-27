#!/usr/bin/env sh
# PayPamin Flow launcher for Linux and other Unix-like systems.
# Copyright © 2026 Rickard Länkvist.
set -eu
APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -n "${PAYPAMIN_PYTHON:-}" ]; then
  PYTHON=$PAYPAMIN_PYTHON
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "PayPamin Flow: Python 3.10 eller senare måste installeras." >&2
  exit 1
fi
exec "$PYTHON" "$APP_DIR/paypamin_flow.pyw" "$@"
