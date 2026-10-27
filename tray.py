"""System-tray integration without importing GUI backends at module import time."""
from __future__ import annotations

from pathlib import Path
from typing import Callable


class TrayUnavailable(RuntimeError):
    """Raised when no usable system-tray backend is available."""


class TrayController:
    """Own one pystray icon and marshal all callbacks onto Tk's main thread."""

    def __init__(
        self,
        *,
        name: str,
        identifier: str,
        icon_path: str | Path,
        scheduler: Callable[[Callable[[], None]], None],
        on_open: Callable[[], None],
        on_exit: Callable[[], None],
        open_label: Callable[[], str],
        exit_label: Callable[[], str],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self.name = name
        self.identifier = identifier
        self.icon_path = Path(icon_path)
        self.scheduler = scheduler
        self.on_open = on_open
        self.on_exit = on_exit
        self.open_label = open_label
        self.exit_label = exit_label
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
            menu = pystray.Menu(
                pystray.MenuItem(lambda item: self.open_label(), lambda icon, item: self._dispatch(self.on_open), default=True),
                pystray.MenuItem(lambda item: self.exit_label(), lambda icon, item: self._dispatch(self.on_exit)),
            )
            icon = pystray.Icon(self.identifier, image, self.name, menu)
        except Exception as exc:
            raise TrayUnavailable(str(exc)) from exc

        self.icon = icon
        try:
            # pystray's run() must own the main thread. run_detached() is its
            # supported integration point when Tk owns the application's main
            # loop; the backend creates and manages its own native event loop.
            # This is required on Windows and macOS and also works on Linux.
            icon.run_detached(setup=self._show_when_ready)
        except Exception as exc:
            self.icon = None
            raise TrayUnavailable(str(exc)) from exc

    def refresh(self) -> None:
        if self.icon is not None:
            self.icon.update_menu()

    def stop(self) -> None:
        self._stopping = True
        icon, self.icon = self.icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
