#!/bin/sh
# PayPamin Flow start file for macOS. Double-click it in Finder.
# Copyright © 2026 Rickard Längkvist.
#
# Finder starts a .command in Terminal. The app is therefore detached straight
# away and this window is closed again, so no console stays open next to the
# window: the app keeps its own log and shows its own dialogues if it cannot
# start.
# One start file serves the whole start: it finds a usable Python and starts the
# app. Python 3.10 or later with Tkinter is required. An existing runtime is
# reused unchanged and is never updated, replaced or shadowed - this script only
# ever *offers* to fetch the latest Python when the system has none, and once a
# usable Python exists the question is never asked at all.
#
# The script never installs anything itself and never touches /usr/bin/python3,
# which belongs to Apple. The offer opens the official download page, so Python
# is installed by the user's own double-click on Apple's or python.org's
# installer.
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TITLE="PayPamin Flow"
MARKER="$HOME/.paminnelseapp/python-offer.declined"
DOWNLOAD_URL="https://www.python.org/downloads/macos/"

NEED_SV="PayPamin Flow behöver Python 3.10 eller senare med Tkinter, men hittar det inte på datorn."
NEED_EN="PayPamin Flow needs Python 3.10 or later with Tkinter, but none was found."
OFFER_SV="Vill du öppna nedladdningssidan för senaste Python? En befintlig Python-installation rörs aldrig."
OFFER_EN="Open the download page for the latest Python? An existing Python installation is never touched."
AFTER_SV="Kör installationsprogrammet och öppna PayPamin Flow igen."
AFTER_EN="Run the installer and open PayPamin Flow again."

# The interpreter must run and be at least 3.10. Tkinter is checked separately
# so a missing window toolkit is never mistaken for a missing Python.
runtime_is_recent() {
  [ -n "${1:-}" ] || return 1
  [ -x "$1" ] || return 1
  "$1" -c 'import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 2)' >/dev/null 2>&1
}

runtime_has_tkinter() {
  "$1" -c 'import tkinter' >/dev/null 2>&1
}

runtime_version() {
  "$1" -c 'import platform; print(platform.python_version())' 2>/dev/null || printf '%s' "okänd"
}

# /usr/bin/python3 is an Apple stub. Without the Command Line Tools it opens a
# system installer dialogue of its own, so it is left untouched instead.
apple_stub_without_tools() {
  [ "$1" = "/usr/bin/python3" ] || return 1
  ! xcode-select -p >/dev/null 2>&1
}

find_python() {
  if [ -n "${PAYPAMIN_PYTHON:-}" ]; then
    if runtime_is_recent "$PAYPAMIN_PYTHON"; then
      printf '%s\n' "$PAYPAMIN_PYTHON"
      return 0
    fi
  fi
  # One name at a time: some shells stop the whole lookup at the first name
  # that does not exist, which would hide a Python that is only called python3.
  for name in python3.13 python3.12 python3.11 python3.10 python3; do
    candidate=$(command -v "$name" 2>/dev/null || true)
    if [ -n "$candidate" ] && runtime_is_recent "$candidate"; then
      if apple_stub_without_tools "$candidate"; then
        continue
      fi
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  for candidate in \
      /opt/homebrew/bin/python3 \
      /usr/local/bin/python3 \
      /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
      /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
      /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \
      /Library/Frameworks/Python.framework/Versions/3.10/bin/python3 \
      /usr/bin/python3; do
    if runtime_is_recent "$candidate"; then
      if apple_stub_without_tools "$candidate"; then
        continue
      fi
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

notify() {
  if command -v osascript >/dev/null 2>&1; then
    if osascript - "$1" "$TITLE" >/dev/null 2>&1 <<'APPLESCRIPT'
on run argv
  set theMessage to item 1 of argv
  set theTitle to item 2 of argv
  display dialog theMessage with title theTitle buttons {"OK"} default button "OK" with icon note
end run
APPLESCRIPT
    then
      return 0
    fi
  fi
  printf '%s\n' "$1" >&2
}

offer_install() {
  if command -v osascript >/dev/null 2>&1; then
    answer=$(osascript - "$1" "$TITLE" 2>/dev/null <<'APPLESCRIPT'
on run argv
  set theMessage to item 1 of argv
  set theTitle to item 2 of argv
  set theAnswer to display dialog theMessage with title theTitle buttons {"Avbryt", "Ladda ner"} default button "Ladda ner" with icon caution
  return button returned of theAnswer
end run
APPLESCRIPT
) || answer=""
    case "$answer" in
      "Ladda ner") return 0 ;;
      *) return 1 ;;
    esac
  fi
  if [ -t 0 ]; then
    printf '%s\n\n' "$1" >&2
    printf 'Öppna nedladdningssidan? [j/N] '
    answer=""
    read -r answer || answer=""
    case "$answer" in
      [jJyY]*) return 0 ;;
      *) return 1 ;;
    esac
  fi
  return 1
}

open_download_page() {
  open "$DOWNLOAD_URL" >/dev/null 2>&1 || true
}

close_own_terminal_window() {
  [ "${TERM_PROGRAM:-}" = "Apple_Terminal" ] || return 0
  command -v osascript >/dev/null 2>&1 || return 0
  # The window is closed only after this script has exited, and only if it is
  # the window Finder opened for this very file.
  (
    sleep 1
    osascript -e 'tell application "Terminal"
      repeat with w in windows
        if name of w contains "start_paypamin_flow.command" then close w
      end repeat
    end tell' >/dev/null 2>&1
  ) >/dev/null 2>&1 &
  return 0
}

if PYTHON=$(find_python); then
  # A runtime that exists is used as it is. Only a missing window toolkit is
  # named, because installing another Python would not help the user here.
  if runtime_has_tkinter "$PYTHON"; then
    nohup "$PYTHON" "$APP_DIR/paypamin_flow_launcher.py" "$@" >/dev/null 2>&1 &
    close_own_terminal_window
    exit 0
  fi
  notify "Python $(runtime_version "$PYTHON") finns på datorn men saknar Tkinter.
Python $(runtime_version "$PYTHON") is installed but Tkinter is missing.

Installera Tcl/Tk till den här tolken, eller använd installationspaketet från python.org som innehåller Tkinter.
Install Tcl/Tk for this interpreter, or use the python.org installer, which includes Tkinter.

$PYTHON"
  exit 1
fi

# The answer is remembered, so a refusal is not repeated on every start.
if [ -f "$MARKER" ]; then
  notify "$NEED_SV
$NEED_EN

Du avböjde nedladdningen tidigare, så frågan ställs inte om.
You declined the download earlier, so the question is not repeated.

$AFTER_SV
$AFTER_EN

$DOWNLOAD_URL"
  exit 1
fi

if offer_install "$NEED_SV
$NEED_EN

$OFFER_SV
$OFFER_EN"; then
  open_download_page
  notify "$AFTER_SV
$AFTER_EN

$DOWNLOAD_URL"
  exit 1
fi

mkdir -p "$(dirname -- "$MARKER")" 2>/dev/null || true
printf 'declined %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || printf 'now')" >"$MARKER" 2>/dev/null || true
notify "$NEED_SV
$NEED_EN

$AFTER_SV
$AFTER_EN

$DOWNLOAD_URL"
exit 1
