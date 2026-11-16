#!/usr/bin/env sh
# PayPamin Flow start file for Linux and other Unix-like systems.
# Copyright © 2026 Rickard Längkvist.
#
# One start file serves the whole start: it finds a usable Python and starts the
# app. Python 3.10 or later with Tkinter is required. An existing runtime is
# reused unchanged and is never updated, replaced or shadowed - this script only
# ever *offers* to fetch the latest Python when the system has none, and once a
# usable Python exists the question is never asked at all.
#
# The script deliberately never runs a package manager and never asks for
# administrator rights: the system Python belongs to the operating system. The
# offer opens the official download page, so the user installs Python with their
# own account.
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TITLE="PayPamin Flow"
MARKER="$HOME/.paminnelseapp/python-offer.declined"
DOWNLOAD_URL="https://www.python.org/downloads/"

NEED_SV="PayPamin Flow behöver Python 3.10 eller senare med Tkinter, men hittar det inte på datorn."
NEED_EN="PayPamin Flow needs Python 3.10 or later with Tkinter, but none was found."
OFFER_SV="Vill du hämta senaste Python från python.org nu? En befintlig Python-installation rörs aldrig."
OFFER_EN="Fetch the latest Python from python.org now? An existing Python installation is never touched."
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

find_python() {
  if [ -n "${PAYPAMIN_PYTHON:-}" ]; then
    if runtime_is_recent "$PAYPAMIN_PYTHON"; then
      printf '%s\n' "$PAYPAMIN_PYTHON"
      return 0
    fi
  fi
  # One name at a time: some shells stop the whole lookup at the first name
  # that does not exist, which would hide a Python that is only called python3.
  for name in python3.13 python3.12 python3.11 python3.10 python3 python; do
    candidate=$(command -v "$name" 2>/dev/null || true)
    if [ -n "$candidate" ] && runtime_is_recent "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  for candidate in /usr/local/bin/python3 /opt/homebrew/bin/python3 /usr/bin/python3; do
    if runtime_is_recent "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

notify() {
  message=$1
  if command -v zenity >/dev/null 2>&1; then
    zenity --info --title "$TITLE" --text "$message" >/dev/null 2>&1 || true
  elif command -v kdialog >/dev/null 2>&1; then
    kdialog --title "$TITLE" --msgbox "$message" >/dev/null 2>&1 || true
  else
    printf '%s\n' "$message" >&2
  fi
}

offer_install() {
  message=$1
  if command -v zenity >/dev/null 2>&1; then
    if zenity --question --title "$TITLE" --text "$message" \
        --ok-label "Hämta Python" --cancel-label "Avbryt" >/dev/null 2>&1; then
      return 0
    fi
    return 1
  fi
  if command -v kdialog >/dev/null 2>&1; then
    if kdialog --title "$TITLE" --yesno "$message" >/dev/null 2>&1; then
      return 0
    fi
    return 1
  fi
  if [ -t 0 ]; then
    printf '%s\n\n' "$message" >&2
    printf 'Hämta senaste Python? [j/N] '
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
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$DOWNLOAD_URL" >/dev/null 2>&1 || true
  fi
}

if PYTHON=$(find_python); then
  # A runtime that exists is used as it is. Only a missing window toolkit is
  # named, because installing another Python would not help the user here.
  if runtime_has_tkinter "$PYTHON"; then
    exec "$PYTHON" "$APP_DIR/paypamin_flow_launcher.py" "$@"
  fi
  notify "Python $(runtime_version "$PYTHON") finns på datorn men saknar Tkinter.
Python $(runtime_version "$PYTHON") is installed but Tkinter is missing.

På Debian/Ubuntu heter paketet python3-tk, på Fedora heter det python3-tkinter.
On Debian/Ubuntu the package is python3-tk, on Fedora it is python3-tkinter.

$PYTHON"
  exit 1
fi

# The answer is remembered, so a refusal is not repeated on every start.
if [ -f "$MARKER" ]; then
  notify "$NEED_SV
$NEED_EN

Du avböjde hämtningen tidigare, så frågan ställs inte om.
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
