"""System-tray integration without importing GUI backends at module import time.

The tray is the app's only permanent entry point on Windows, macOS and Linux,
so this module also explains *why* a tray was unavailable instead of leaving
the user with a silent failure. Behaviour differences between the platforms
are documented next to the code that depends on them.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable


class TrayUnavailable(RuntimeError):
    """Raised when no usable system-tray backend is available."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


def backend_hint(error: Exception) -> str:
    """Return a platform-specific explanation for a missing tray backend.

    pystray tries the AppIndicator, GTK and plain X11 backends on Linux and
    needs the native equivalents on Windows and macOS. When every candidate
    fails the user sees the real reason plus what to install, which matters on
    Wayland sessions where a tray icon is not available without AppIndicator
    support.
    """
    text = str(error)
    if sys.platform.startswith("win"):
        return (
            "Windows: kontrollera att appen startades som ett skrivbordsprogram "
            "och inte i en tjänstesession."
        )
    if sys.platform == "darwin":
        return (
            "macOS: systemfältet kräver en grafisk inloggningssession. "
            "Starta appen från Finder eller terminalen i din egen session."
        )
    return (
        "Linux: systemfältet kräver AppIndicator-stöd (paketet "
        "'gir1.2-ayatanaappindicator3-0.1' eller 'libappindicator3-1') och en "
        "panel som visar statusikoner. Under Wayland behövs dessutom tillägget "
        "AppIndicator/KStatusNotifierItem i skrivbordsmiljön. Saknas stödet "
        "fungerar appen som vanligt, men fönstret stängs till aktivitetsfältet "
        "i stället för att döljas."
    ) + (f" Teknisk orsak: {text}" if text else "")


class TrayController:
    """Own one pystray icon and marshal all callbacks onto Tk's main thread.

    Menu order is fixed and documented in the tests: status, open, scan
    import folder, open export folder, update, separator, full exit. Every
    item is optional except open and exit, so a backend without separators or
    with a reduced menu still works.
    """

    def __init__(
        self,
        *,
        name: str,
        identifier: str,
        icon_path: str | Path,
        scheduler: Callable[[Callable[[], None]], None],
        on_open: Callable[[], None],
        on_update: Callable[[], None],
        on_exit: Callable[[], None],
        open_label: Callable[[], str],
        update_label: Callable[[], str],
        exit_label: Callable[[], str],
        on_scan: Callable[[], None] | None = None,
        on_export: Callable[[], None] | None = None,
        scan_label: Callable[[], str] | None = None,
        export_label: Callable[[], str] | None = None,
        status_label: Callable[[], str] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self.name = name
        self.identifier = identifier
        self.icon_path = Path(icon_path)
        self.scheduler = scheduler
        self.on_open = on_open
        self.on_update = on_update
        self.on_exit = on_exit
        self.open_label = open_label
        self.update_label = update_label
        self.exit_label = exit_label
        self.on_scan = on_scan
        self.on_export = on_export
        self.scan_label = scan_label
        self.export_label = export_label
        self.status_label = status_label
        self.on_error = on_error
        self.icon = None
        self._stopping = False

    @property
    def running(self) -> bool:
        return self.icon is not None

    def _dispatch(self, callback: Callable[[], None]) -> None:
        if self._stopping:
            return
        try:
            self.scheduler(callback)
        except Exception:
            # Tk may already have been destroyed by an explicit full exit.
            pass

    def _status_text(self) -> str:
        if self.status_label is None:
            return ""
        try:
            return str(self.status_label() or "")
        except Exception:
            return ""

    def _menu(self, pystray):
        items = []
        if self.status_label is not None:
            items.append(pystray.MenuItem(
                lambda item: self._status_text() or self.name,
                None,
                enabled=False,
            ))
        items.append(pystray.MenuItem(
            lambda item: self.open_label(),
            lambda icon, item: self._dispatch(self.on_open),
            default=True,
        ))
        if self.on_scan is not None and self.scan_label is not None:
            items.append(pystray.MenuItem(
                lambda item: self.scan_label(),
                lambda icon, item: self._dispatch(self.on_scan),
            ))
        if self.on_export is not None and self.export_label is not None:
            items.append(pystray.MenuItem(
                lambda item: self.export_label(),
                lambda icon, item: self._dispatch(self.on_export),
            ))
        items.append(pystray.MenuItem(
            lambda item: self.update_label(),
            lambda icon, item: self._dispatch(self.on_update),
        ))
        separator = getattr(pystray, "Menu", None)
        if separator is not None and hasattr(pystray, "MenuItem"):
            try:
                items.append(pystray.Menu.SEPARATOR)
            except Exception:
                pass
        items.append(pystray.MenuItem(
            lambda item: self.exit_label(),
            lambda icon, item: self._dispatch(self.on_exit),
        ))
        return pystray.Menu(*items)

    def _show_when_ready(self, icon) -> None:
        """Make the icon visible from pystray's ready callback."""
        try:
            # A custom setup callback must set visible itself. The callback is
            # invoked only after the backend has created its native tray item.
            icon.visible = True
        except Exception as exc:
            if not self._stopping and self.on_error:
                self._dispatch(lambda error=exc: self.on_error(error))

    def start(self) -> None:
        if self.icon is not None:
            return
        self._stopping = False
        try:
            import pystray
            from PIL import Image

            with Image.open(self.icon_path) as source:
                image = source.convert("RGBA").copy()
            menu = self._menu(pystray)
            icon = pystray.Icon(self.identifier, image, self.name, menu)
        except Exception as exc:
            raise TrayUnavailable(str(exc), backend_hint(exc)) from exc

        self.icon = icon
        try:
            # pystray's run() must own the main thread. run_detached() is its
            # supported integration point when Tk owns the application's main
            # loop; the backend creates and manages its own native event loop.
            # This is required on Windows and macOS and also works on Linux.
            icon.run_detached(setup=self._show_when_ready)
        except Exception as exc:
            self.icon = None
            raise TrayUnavailable(str(exc), backend_hint(exc)) from exc

    def refresh(self) -> None:
        if self.icon is not None:
            self.icon.update_menu()

    def set_title(self, text: str) -> None:
        """Update the tray tooltip without rebuilding the menu."""
        if self.icon is None or not text:
            return
        try:
            self.icon.title = text
        except Exception:
            pass

    def notify(self, message: str, title: str | None = None) -> bool:
        """Show a tray balloon if the backend supports it; never raise.

        Balloon notifications are optional: X11 and some AppIndicator versions
        do not implement them, and a missing notification must never prevent
        the app from hiding to the tray.
        """
        if self.icon is None:
            return False
        try:
            self.icon.notify(message, title or self.name)
            return True
        except Exception:
            return False

    def stop(self) -> None:
        self._stopping = True
        icon, self.icon = self.icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
