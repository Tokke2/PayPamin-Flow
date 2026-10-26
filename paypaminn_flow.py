"""Backward-compatible imports for the former paypaminn_flow module name.

Parsing stays available without Tkinter. Other attributes are loaded lazily from
paypamin_flow when requested. New code should use paypamin_flow or invoice_parser.
"""
from importlib import import_module

from invoice_parser import extract_pdf, normalize_amount, normalize_date, parse_invoice_text

__all__ = ["extract_pdf", "normalize_amount", "normalize_date", "parse_invoice_text", "main"]


def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module("paypamin_flow")
    try:
        return getattr(module, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc


def main():
    return import_module("paypamin_flow").main()
