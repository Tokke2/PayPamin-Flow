"""Record the failures that a bare ``pass`` used to hide.

A GUI has hundreds of places where an exception is genuinely uninteresting:
a widget that was already destroyed, a temporary file that had already been
removed, a callback that fired after its window closed. Writing those as
``except TclError: pass`` keeps the user interface calm, but it also means a
real fault can disappear without a trace - and the consolidated error log,
which is the only thing the author gets to see from a user's machine, would
never learn about it.

Every such site now calls :func:`report_fault` instead. The severity follows
the *type* of the error, not the place it was caught:

* ``TclError`` and the ``OSError`` family are the expected ones - a closed
  window, a file that is already gone. They are written once per site to
  ``app.log`` as a warning, without a traceback, because there is nothing to
  fix.
* Anything else (a ``ValueError``, a ``KeyError``, an ``AttributeError``) is a
  defect. It is written once per site to ``app.log`` as an error *with* its
  traceback, and ``errors.log`` therefore picks it up as an unresolved error.

Repeats are counted, not printed: a scroll callback can fail on every pixel and
still leave three lines in the log plus one line in the summary. Nothing here
ever raises - a logging failure must not turn into the crash it was meant to
report.
"""
from __future__ import annotations

import logging
import sys

from app_info import APP_SLUG

LOGGER_NAME = f"{APP_SLUG}.quiet"

# Names rather than imports: tkinter is not installed everywhere this module is
# used (the test suite runs without it), and a name check is enough to tell the
# toolkit's teardown noise from a real defect.
_EXPECTED_NAMES = frozenset({"TclError"})
_EXPECTED_OS_ERRORS = (OSError,)

_MAX_MESSAGE = 240
_counts: dict[tuple[str, str], dict[str, object]] = {}
_order: list[tuple[str, str]] = []


def _site(depth: int = 1) -> str:
    """Return ``module:function`` of the caller, for grouping repeats."""
    try:
        frame = sys._getframe(depth + 1)
    except (AttributeError, ValueError):  # pragma: no cover - exotic runtimes
        return "?"
    module = str(frame.f_globals.get("__name__", "?"))
    return f"{module}:{frame.f_code.co_name}"


def is_expected(error: BaseException | None) -> bool:
    """Return whether this error is part of normal shutdown or cleanup."""
    if error is None:
        return True
    if type(error).__name__ in _EXPECTED_NAMES:
        return True
    return isinstance(error, _EXPECTED_OS_ERRORS)


def severity_for(error: BaseException | None, level: int | None = None) -> int:
    """Return the level a fault of this type deserves."""
    if level is not None:
        return level
    return logging.WARNING if is_expected(error) else logging.ERROR


def _message(error: BaseException | None) -> str:
    text = str(error or "").replace("\n", " ").strip()
    return text[:_MAX_MESSAGE]


def report_fault(
    error: BaseException | None = None,
    *,
    level: int | None = None,
    site: str = "",
) -> None:
    """Note a swallowed exception without letting logging fail the caller.

    The first occurrence of a given (site, type) pair is written to the log;
    the rest only increment a counter that :func:`summary` reports. Pass
    ``error`` when the handler does not bind one; otherwise the exception being
    handled is read from ``sys.exc_info()``.
    """
    try:
        if error is None:
            error = sys.exc_info()[1]
        site = site or _site(1)
        name = type(error).__name__ if error is not None else "None"
        key = (site, name)
        entry = _counts.get(key)
        if entry is not None:
            entry["count"] = int(entry["count"]) + 1  # type: ignore[arg-type]
            entry["last"] = _message(error)
            return
        logger = logging.getLogger(LOGGER_NAME)
        resolved = severity_for(error, level)
        entry = {
            "count": 1,
            "level": resolved,
            "message": _message(error),
            "last": _message(error),
        }
        _counts[key] = entry
        _order.append(key)
        # ``exc_info=True`` outside an ``except`` block would print the useless
        # "NoneType: None"; an error that was handed over has its own traceback
        # or none at all.
        trace = (type(error), error, error.__traceback__) if error is not None and error.__traceback__ else False
        if resolved >= logging.ERROR:
            logger.error(
                "Swallowed %s at %s: %s", name, site, entry["message"], exc_info=trace
            )
        else:
            logger.warning("Swallowed %s at %s: %s", name, site, entry["message"])
    except Exception:  # noqa: BLE001 - reporting must never raise
        return None


def summary() -> list[str]:
    """Return one readable line per distinct swallowed fault."""
    lines = []
    for key in _order:
        entry = _counts.get(key)
        if entry is None:
            continue
        site, name = key
        count = int(entry["count"])  # type: ignore[arg-type]
        message = str(entry["message"])
        if count > 1:
            last = str(entry["last"])
            tail = f" (senast: {last})" if last and last != message else ""
            lines.append(f"{site}: {name} x{count}{tail}")
        else:
            lines.append(f"{site}: {name}: {message}" if message else f"{site}: {name}")
    return lines


def log_summary(logger: logging.Logger | None = None) -> list[str]:
    """Write the summary to ``app.log`` and return what was written."""
    lines = summary()
    if not lines:
        return lines
    target = logger or logging.getLogger(APP_SLUG)
    try:
        target.info("Swallowed faults this session: %d site(s)", len(lines))
        for line in lines:
            target.info("  %s", line)
    except Exception:  # noqa: BLE001 - logging must never raise here
        return lines
    return lines


def reset() -> None:
    """Forget what has been recorded (tests, and a fresh start after a reload)."""
    _counts.clear()
    _order.clear()
