#!/usr/bin/env sh
# Install a built PayPamin Flow binary and its Linux desktop icon for this user.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BINARY=${1:-"$ROOT/dist/paypamin-flow"}
PREFIX=${PREFIX:-"$HOME/.local"}
if [ ! -f "$BINARY" ]; then
  echo "Bygg först med: pyinstaller paypamin_flow.spec --clean --noconfirm" >&2
  exit 1
fi
install -D -m 755 "$BINARY" "$PREFIX/bin/paypamin-flow"
install -D -m 644 "$ROOT/assets/paypamin_flow.png" "$PREFIX/share/icons/hicolor/256x256/apps/paypamin-flow.png"
install -D -m 644 "$ROOT/packaging/paypamin-flow.desktop" "$PREFIX/share/applications/paypamin-flow.desktop"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$PREFIX/share/applications" >/dev/null 2>&1 || true
fi
printf '%s\n' "PayPamin Flow installerades för $USER." "Starta via programmenyn eller kommandot paypamin-flow."
