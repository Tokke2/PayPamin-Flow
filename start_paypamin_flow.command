#!/usr/bin/env sh
# Double-clickable PayPamin Flow source launcher for macOS.
# Copyright © 2026 Rickard Länkvist.
set -eu
APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$APP_DIR/start_paypamin_flow.sh" "$@"
