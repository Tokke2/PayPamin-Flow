#!/usr/bin/env sh
# Install the Python source app and its Linux desktop icon for this user.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PREFIX=${PREFIX:-"$HOME/.local"}
APP_HOME="$PREFIX/share/paypamin-flow"
PYTHON=${PYTHON:-python3}
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  printf '%s\n' "Python 3 måste vara installerat innan PayPamin Flow installeras." >&2
  exit 1
fi
mkdir -p "$APP_HOME/assets" "$APP_HOME/packaging" "$PREFIX/bin"
for FILE in "$ROOT"/*.py "$ROOT"/*.pyw "$ROOT"/requirements.txt; do
  [ ! -f "$FILE" ] || install -m 644 "$FILE" "$APP_HOME/$(basename -- "$FILE")"
done
cp -R "$ROOT/assets/." "$APP_HOME/assets/"
install -m 644 "$ROOT/packaging/paypamin-flow.desktop" "$APP_HOME/packaging/paypamin-flow.desktop"
LAUNCHER="$PREFIX/bin/paypamin-flow"
printf '%s\n' '#!/bin/sh' "exec \"$PYTHON\" \"$APP_HOME/paypamin_flow.py\" \"\$@\"" > "$LAUNCHER"
chmod 755 "$LAUNCHER"
install -D -m 644 "$ROOT/assets/paypamin_flow.png" "$PREFIX/share/icons/hicolor/256x256/apps/paypamin-flow.png"
install -D -m 644 "$ROOT/packaging/paypamin-flow.desktop" "$PREFIX/share/applications/paypamin-flow.desktop"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$PREFIX/share/applications" >/dev/null 2>&1 || true
fi
printf '%s\n' "PayPamin Flow installerades för $USER." "Starta via programmenyn eller kommandot paypamin-flow."
