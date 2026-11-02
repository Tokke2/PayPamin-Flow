"""Structured, non-invasive activity tracing for PayPamin Flow."""
from __future__ import annotations

import json
import logging
import math
import time
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path

from app_info import APP_SLUG


_SESSION_ID = uuid.uuid4().hex[:16]
_WRAPPED_ATTRIBUTE = "_paypamin_activity_wrapped"


def _safe(value, depth=0):
    """Convert diagnostic values to bounded JSON without exposing object repr dumps."""
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, (str, Path)):
        text = str(value)
        return text if len(text) <= 4000 else text[:3997] + "..."
    if depth >= 4:
        return str(type(value).__name__)
    if isinstance(value, dict):
        items = list(value.items())[:100]
        return {str(key)[:200]: _safe(item, depth + 1) for key, item in items}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_safe(item, depth + 1) for item in list(value)[:100]]
    return str(type(value).__name__)


def log_activity(component, action, status="completed", *, level=logging.INFO, exc_info=False, **details):
    """Write one structured event through the existing technical-log handlers."""
    event = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "session_id": _SESSION_ID,
        "component": str(component),
        "action": str(action),
        "status": str(status),
        "details": _safe(details),
    }
    try:
        logging.getLogger(APP_SLUG).log(
            level,
            "Activity: %s",
            json.dumps(event, ensure_ascii=False, sort_keys=True),
            exc_info=exc_info,
        )
    except Exception:
        # Diagnostics must never prevent the underlying application action.
        pass
    return event


def instrument_action(callback, label, component="ui"):
    """Trace a Tk command's start, completion or failure without changing its result."""
    if getattr(callback, _WRAPPED_ATTRIBUTE, False):
        return callback
    action_label = str(label or getattr(callback, "__name__", "unknown"))

    @wraps(callback)
    def traced(*args, **kwargs):
        action_id = uuid.uuid4().hex[:16]
        log_activity(component, action_label, "started", action_id=action_id)
        started = time.perf_counter()
        try:
            result = callback(*args, **kwargs)
        except Exception as exc:
            log_activity(
                component,
                action_label,
                "error",
                level=logging.ERROR,
                exc_info=True,
                action_id=action_id,
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                error_type=type(exc).__name__,
                error=str(exc),
            )
            raise
        log_activity(
            component,
            action_label,
            "completed",
            action_id=action_id,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            result_type=type(result).__name__,
        )
        return result

    setattr(traced, _WRAPPED_ATTRIBUTE, True)
    return traced


def instrument_tk_command(owner, command, label, component="ui"):
    """Wrap either a Python callback or Tk's registered command name."""
    if callable(command):
        return instrument_action(command, label, component)
    if not str(command or "").strip():
        return command

    def invoke_registered_command():
        return owner.tk.call(command)

    return instrument_action(invoke_registered_command, label, component)
