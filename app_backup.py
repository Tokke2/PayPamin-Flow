"""Local, validated backups for PayPamin Flow settings and reminders.

Backups contain a consistent SQLite snapshot together with generated reminder
PDFs and supplier logos. No logs, imported invoice PDFs, or application code are
included. Restoring always creates a safety backup of the current data first.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import uuid
import zipfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from app_info import APP_NAME, APP_VERSION
from i18n import _

BACKUP_FORMAT = 1
DATABASE_MEMBER = "data/paminnelseapp.sqlite3"
MANIFEST_MEMBER = "manifest.json"
MAX_BACKUP_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_BACKUP_MEMBERS = 20_000


class BackupError(RuntimeError):
    """Raised when a backup cannot be created or safely restored."""


@dataclass(frozen=True)
class BackupPaths:
    """Locations of the user-owned data included in a backup."""

    database: Path
    export_dir: Path
    svg_dir: Path
    safety_dir: Path


def suggested_backup_filename(now: datetime | None = None) -> str:
    moment = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"PayPamin-Flow-backup-{moment}.zip"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _snapshot_database(source_path: Path, destination: Path) -> None:
    if not source_path.is_file():
        raise BackupError(_("Databasen saknas."))
    try:
        with closing(sqlite3.connect(source_path)) as source:
            with closing(sqlite3.connect(destination)) as target:
                source.backup(target)
                target.commit()
        _validate_database(destination)
    except (sqlite3.Error, OSError) as exc:
        raise BackupError(_("Databasen kunde inte kopieras: {error}", error=exc)) from exc


def _validate_database(path: Path) -> None:
    try:
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("PRAGMA query_only=ON")
            result = connection.execute("PRAGMA integrity_check").fetchone()
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
    except sqlite3.Error as exc:
        raise BackupError(_("Säkerhetskopian innehåller ingen giltig databas: {error}", error=exc)) from exc
    if not result or result[0] != "ok":
        raise BackupError(_("Databasen i säkerhetskopian är skadad."))
    if not {"settings", "invoices"}.issubset(tables):
        raise BackupError(_("Säkerhetskopian saknar PayPamin Flows inställningar eller fakturor."))


def _user_files(root: Path, prefix: str, excluded: set[Path] | None = None):
    excluded = excluded or set()
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        if path.resolve() in excluded:
            continue
        relative = path.relative_to(root).as_posix()
        yield path, f"{prefix}/{relative}"


def create_backup(
    destination: str | Path,
    paths: BackupPaths,
    *,
    app_version: str = APP_VERSION,
) -> Path:
    """Create a backup atomically and return its final path."""

    destination = Path(destination).expanduser().resolve()
    if destination.suffix.lower() != ".zip":
        destination = destination.with_suffix(".zip")
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary_name: str | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="paypamin-backup-") as temporary:
            staging = Path(temporary)
            database = staging / "database.sqlite3"
            _snapshot_database(paths.database, database)

            payloads: list[tuple[Path, str]] = [(database, DATABASE_MEMBER)]
            excluded = {destination}
            payloads.extend(_user_files(paths.export_dir, "export", excluded) or ())
            payloads.extend(_user_files(paths.svg_dir, "svg", excluded) or ())
            manifest = {
                "application": APP_NAME,
                "format": BACKUP_FORMAT,
                "app_version": app_version,
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "files": {member: _sha256(path) for path, member in payloads},
            }

            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
            )
            os.close(descriptor)
            with zipfile.ZipFile(
                temporary_name, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
            ) as archive:
                archive.writestr(
                    MANIFEST_MEMBER,
                    json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
                )
                for path, member in payloads:
                    archive.write(path, member)
            os.replace(temporary_name, destination)
            temporary_name = None
            try:
                destination.chmod(0o600)
            except OSError:
                pass
            return destination
    except BackupError:
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        raise BackupError(_("Säkerhetskopian kunde inte skapas: {error}", error=exc)) from exc
    finally:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def _validate_member(info: zipfile.ZipInfo) -> str:
    name = info.filename
    path = PurePosixPath(name)
    if (
        not name
        or name.endswith("/")
        or "\\" in name
        or path.is_absolute()
        or ".." in path.parts
        or any(part in ("", ".") for part in path.parts)
    ):
        raise BackupError(_("Säkerhetskopian innehåller en osäker filsökväg."))
    mode = info.external_attr >> 16
    if mode and stat.S_ISLNK(mode):
        raise BackupError(_("Säkerhetskopian innehåller en symbolisk länk."))
    if not (
        name in (MANIFEST_MEMBER, DATABASE_MEMBER)
        or name.startswith("export/")
        or name.startswith("svg/")
    ):
        raise BackupError(_("Filen är inte tillåten i en säkerhetskopia: {name}", name=name))
    return name


def _read_backup(archive_path: Path, staging: Path) -> tuple[Path, Path, Path]:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_BACKUP_MEMBERS:
                raise BackupError(_("Säkerhetskopian innehåller för många filer."))
            if sum(info.file_size for info in infos) > MAX_BACKUP_UNCOMPRESSED_BYTES:
                raise BackupError(_("Säkerhetskopian är för stor för att återställas säkert."))
            names = [_validate_member(info) for info in infos]
            if len(names) != len(set(names)):
                raise BackupError(_("Säkerhetskopian innehåller dubbletter av filnamn."))
            if MANIFEST_MEMBER not in names or DATABASE_MEMBER not in names:
                raise BackupError(_("Säkerhetskopian saknar manifest eller databas."))
            try:
                manifest = json.loads(archive.read(MANIFEST_MEMBER).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BackupError(_("Säkerhetskopians manifest är ogiltigt.")) from exc
            if (
                manifest.get("application") != APP_NAME
                or manifest.get("format") != BACKUP_FORMAT
                or not isinstance(manifest.get("files"), dict)
            ):
                raise BackupError(_("Detta är inte en säkerhetskopia från PayPamin Flow."))
            expected_files = manifest["files"]
            if set(expected_files) != set(names) - {MANIFEST_MEMBER}:
                raise BackupError(_("Säkerhetskopians filista stämmer inte med innehållet."))

            for info in infos:
                name = info.filename
                if name == MANIFEST_MEMBER:
                    continue
                target = staging / PurePosixPath(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
                expected_hash = expected_files.get(name)
                if not isinstance(expected_hash, str) or _sha256(target) != expected_hash:
                    raise BackupError(_("Kontrollsumman stämmer inte för: {name}", name=name))
    except BackupError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise BackupError(_("Säkerhetskopian kunde inte läsas: {error}", error=exc)) from exc

    database = staging / DATABASE_MEMBER
    _validate_database(database)
    return database, staging / "export", staging / "svg"


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _install_replacement(source: Path, target: Path, *, directory: bool):
    """Install one file/tree, retaining its predecessor for rollback."""

    target.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    replacement = target.parent / f".{target.name}.restoring-{token}"
    previous = target.parent / f".{target.name}.previous-{token}"
    if directory:
        if source.is_dir():
            shutil.copytree(source, replacement)
        else:
            replacement.mkdir()
    else:
        shutil.copy2(source, replacement)
    existed = target.exists()
    if existed:
        os.replace(target, previous)
    try:
        os.replace(replacement, target)
    except Exception:
        if existed and previous.exists():
            os.replace(previous, target)
        _remove(replacement)
        raise
    return target, previous, existed


def _rollback(installed) -> None:
    for target, previous, existed in reversed(installed):
        _remove(target)
        if existed and previous.exists():
            os.replace(previous, target)


def _discard_predecessors(installed) -> None:
    for _, previous, _ in installed:
        try:
            _remove(previous)
        except OSError:
            # The restore is already complete; leftover hidden predecessors
            # can be removed later and must not be reported as data loss.
            pass


def restore_backup(archive: str | Path, paths: BackupPaths) -> Path:
    """Validate and restore a backup, returning the pre-restore safety copy."""

    archive = Path(archive).expanduser().resolve()
    if not archive.is_file():
        raise BackupError(_("Välj en befintlig säkerhetskopia."))
    paths.safety_dir.mkdir(parents=True, exist_ok=True)
    installed = []
    try:
        with tempfile.TemporaryDirectory(prefix="paypamin-restore-") as temporary:
            database, export, svg = _read_backup(archive, Path(temporary))
            safety_name = f"pre-restore-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.zip"
            safety = create_backup(paths.safety_dir / safety_name, paths)
            try:
                installed.append(
                    _install_replacement(database, paths.database, directory=False)
                )
                installed.append(
                    _install_replacement(export, paths.export_dir, directory=True)
                )
                installed.append(
                    _install_replacement(svg, paths.svg_dir, directory=True)
                )
            except Exception:
                _rollback(installed)
                raise
            _discard_predecessors(installed)
            return safety
    except BackupError:
        raise
    except (OSError, sqlite3.Error, shutil.SameFileError) as exc:
        raise BackupError(_("Återställningen misslyckades: {error}", error=exc)) from exc
