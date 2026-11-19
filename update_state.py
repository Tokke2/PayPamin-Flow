"""What the installed copy contains, so an update is judged by its files.

A version number cannot describe a republished build: this project stays on
0.6.0 while it is being finished, rebuilds the release and replaces the ZIP in
place. The only honest question is therefore whether the files differ, so this
module remembers which package the app was installed from and compares the
installed files with the files inside a release package.

Nothing here touches the screen or the network; the caller supplies a directory
and, when it has one, a downloaded package index.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app_info import is_python_package_file
from quiet_faults import report_fault

STATE_FILENAME = "installed-release.json"
MAX_STATE_BYTES = 64 * 1024
_HEX_DIGITS = frozenset("0123456789abcdef")
# build_info.py is stamped per build: the value inside the repository, a source
# checkout and the ZIP built from it differ, so it can never decide whether the
# application itself has changed.
IGNORED_FILES = frozenset({"build_info.py"})


def is_sha256(value) -> bool:
    """Return whether ``value`` is a complete lowercase SHA-256 hex digest."""
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(character in _HEX_DIGITS for character in text)


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def state_path(directory=None) -> Path:
    """Return the state file inside the application's data directory."""
    base = Path(directory) if directory else Path.home() / ".paminnelseapp"
    return base / STATE_FILENAME


def read_state(path=None) -> dict:
    """Return the recorded install state, or an empty dict when there is none.

    A corrupt or oversized file is treated as "unknown", never as an error: an
    update check must not fail because a bookkeeping file was damaged.
    """
    target = Path(path) if path else state_path()
    try:
        if target.stat().st_size > MAX_STATE_BYTES:
            return {}
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    state = {}
    for key in ("package_sha256", "source_commit", "release_id", "version", "files_fingerprint", "checked_at"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            state[key] = value.strip()
    if state.get("package_sha256") and not is_sha256(state["package_sha256"]):
        state.pop("package_sha256")
    if state.get("source_commit") and not is_commit(state["source_commit"]):
        state.pop("source_commit")
    return state


def write_state(values, path=None) -> bool:
    """Write the state atomically, so a crash never leaves half a JSON file."""
    target = Path(path) if path else state_path()
    payload = {key: value for key, value in dict(values or {}).items() if isinstance(value, str) and value}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, target)
        finally:
            try:
                Path(temporary_name).unlink()
            except OSError:
                report_fault()
        return True
    except OSError:
        return False


def clear_state(path=None) -> bool:
    try:
        target = Path(path) if path else state_path()
        target.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def restore_state(previous, path=None) -> bool:
    """Put a previous record back after a rolled-back installation."""
    if previous:
        return write_state(previous, path)
    return clear_state(path)


def is_commit(value) -> bool:
    """Return whether a value is a full 40-character git commit."""
    return bool(re.fullmatch(r"[0-9a-f]{40}", str(value or "").strip().lower()))


def record_installed_package(
    package_sha256="",
    *,
    release_id: str = "",
    version: str = "",
    files_fingerprint: str = "",
    source_commit: str = "",
    path=None,
) -> bool:
    """Remember the release the running files came from.

    ``source_commit`` is the important value now that the release is the source
    archive at a tag: it names the exact code on disk, so the next check is a
    string comparison instead of a download. The package hash is still recorded
    for an installation that came from a ZIP.
    """
    digest = str(package_sha256 or "").strip().lower()
    commit = str(source_commit or "").strip().lower()
    if digest and not is_sha256(digest):
        return False
    if not digest and not is_commit(commit):
        return False
    values = {
        "package_sha256": digest if is_sha256(digest) else "",
        "source_commit": commit if is_commit(commit) else "",
        "release_id": str(release_id or "").strip(),
        "version": str(version or "").strip(),
        "files_fingerprint": str(files_fingerprint or "").strip().lower(),
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    return write_state(values, path)


def installed_package_sha256(path=None) -> str:
    value = read_state(path).get("package_sha256", "")
    return value.lower() if is_sha256(value) else ""


def installed_source_commit(path=None) -> str:
    """Return the commit the installed files were taken from, if recorded."""
    value = read_state(path).get("source_commit", "")
    return value.lower() if is_commit(value) else ""


def is_source_checkout(directory) -> bool:
    """Return whether the running files live in a git working tree.

    A checkout is the developer's own copy: the release is then normally older
    than the files on disk, so an automatic installation would silently undo
    work. The files are still compared and an update can still be installed,
    but only after the user has read the warning.
    """
    try:
        return (Path(directory) / ".git").exists()
    except OSError:
        return False


def local_package_hashes(directory, names=None) -> dict:
    """Return SHA-256 for the shipped files present in ``directory``.

    Hidden directories are never entered: ``.git`` can hold tens of thousands
    of objects and none of them is an application file.
    """
    root = Path(directory)
    wanted = None if names is None else {str(name) for name in names}
    hashes = {}
    for current, folders, files in os.walk(root):
        folders[:] = sorted(folder for folder in folders if not folder.startswith("."))
        base = Path(current)
        for filename in sorted(files):
            path = base / filename
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                continue
            if relative in IGNORED_FILES or not is_python_package_file(relative):
                continue
            if wanted is not None and relative not in wanted:
                continue
            try:
                hashes[relative] = sha256_file(path)
            except OSError:
                continue
    return hashes


@dataclass(frozen=True)
class PackageDiff:
    """Which files in a release differ from the installed copy."""

    changed: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()

    @property
    def files(self) -> tuple[str, ...]:
        """Every file that would be written by installing the release."""
        return tuple(sorted(set(self.changed) | set(self.missing)))

    def __bool__(self) -> bool:
        return bool(self.changed or self.missing)


def compare_package_files(release_hashes, directory) -> PackageDiff:
    """Compare a release's per-file hashes with the files on disk.

    Only files that the release ships are compared; a checkout's tests,
    documentation and git metadata are none of the release's business. A file
    the release has and the disk lacks counts as changed, because installing
    would create it.
    """
    root = Path(directory)
    installed = local_package_hashes(root, names=release_hashes.keys())
    changed = []
    missing = []
    for name, expected in sorted(dict(release_hashes).items()):
        if name in IGNORED_FILES:
            continue
        actual = installed.get(name)
        if actual is None:
            missing.append(name)
        elif not is_sha256(expected) or actual != expected.strip().lower():
            changed.append(name)
    return PackageDiff(changed=tuple(changed), missing=tuple(missing))


def newest_local_mtime(directory, names=None) -> float:
    """Return the newest modification time among the shipped files on disk."""
    root = Path(directory)
    newest = 0.0
    wanted = None if names is None else {str(name) for name in names}
    for current, folders, files in os.walk(root):
        folders[:] = sorted(folder for folder in folders if not folder.startswith("."))
        base = Path(current)
        for filename in files:
            path = base / filename
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                continue
            if relative in IGNORED_FILES or not is_python_package_file(relative):
                continue
            if wanted is not None and relative not in wanted:
                continue
            try:
                newest = max(newest, path.stat().st_mtime)
            except OSError:
                continue
    return newest


def describe_files(files, limit: int = 4) -> str:
    """Name a few files for a dialog, without ever growing a long list."""
    names = list(files)
    if not names:
        return ""
    shown = ", ".join(names[:limit])
    if len(names) > limit:
        shown = f"{shown} … (+{len(names) - limit})"
    return shown
