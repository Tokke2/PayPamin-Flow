"""Conservative text and identifier matching for supplier profiles.

Organisation and bankgiro numbers in running text are matched only when they
have an explicit label. A number explicitly isolated by a user-drawn template
zone may instead be bare. This module handles names and textual SVG aliases;
visual PDF/SVG logo comparison is isolated in :mod:`logo_matching`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class SupplierMatch:
    vendor: str
    method: str
    score: int


_ORG_PATTERN = re.compile(
    r"\b(?:org(?:anisations)?\.?[\s\-–—‑]*(?:nr|nummer|no\.?)|"
    r"organisation\s*(?:number|no\.?)|organization\s*(?:number|no\.?))"
    r"\s*[:#]?\s*(?<![0-9])([0-9]{6}[\s\-–—]?[0-9]{4})(?![0-9])",
    re.IGNORECASE,
)
_BANKGIRO_PATTERN = re.compile(
    r"\b(?:bankgiro(?:[\s\-–—‑]*(?:nr|nummer|no\.?))?|"
    r"bg\.?[\s\-–—‑]*(?:nr|nummer|no\.?)?)"
    r"\s*[:#]?\s*(?<![0-9])([0-9]{3,4}[\s\-–—]?[0-9]{4})(?![0-9])",
    re.IGNORECASE,
)
_COMPANY_SUFFIXES = {
    "ab", "aktiebolag", "hb", "kb", "as", "asa", "oy", "oyj", "abp",
    "gmbh", "ltd", "limited", "bv", "nv", "aps", "inc",
}
_GENERIC_LOGO_NAMES = {"logo", "logotyp", "vendor", "supplier", "company", "faktura", "invoice"}


def _normalized(value) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def normalize_org_number(value) -> str:
    """Return a Swedish organisation number as ten ASCII digits."""
    text = _normalized(value)
    if not text:
        return ""
    if not re.fullmatch(r"[0-9\s\-–—]+", text):
        raise ValueError("Invalid organisation number")
    digits = re.sub(r"[^0-9]", "", text)
    if len(digits) != 10:
        raise ValueError("Invalid organisation number")
    return digits


def normalize_bankgiro_number(value) -> str:
    """Return a seven- or eight-digit bankgiro number without separators."""
    text = _normalized(value)
    if not text:
        return ""
    if not re.fullmatch(r"[0-9\s\-–—]+", text):
        raise ValueError("Invalid bankgiro number")
    digits = re.sub(r"[^0-9]", "", text)
    if len(digits) not in (7, 8):
        raise ValueError("Invalid bankgiro number")
    return digits


def format_org_number(value) -> str:
    digits = normalize_org_number(value)
    return f"{digits[:6]}-{digits[6:]}" if digits else ""


def format_bankgiro_number(value) -> str:
    digits = normalize_bankgiro_number(value)
    return f"{digits[:-4]}-{digits[-4:]}" if digits else ""


def extract_org_numbers(text) -> set[str]:
    values = set()
    for match in _ORG_PATTERN.finditer(_normalized(text)):
        try:
            values.add(normalize_org_number(match.group(1)))
        except ValueError:
            pass
    return values


def extract_bankgiro_numbers(text) -> set[str]:
    values = set()
    for match in _BANKGIRO_PATTERN.finditer(_normalized(text)):
        try:
            values.add(normalize_bankgiro_number(match.group(1)))
        except ValueError:
            pass
    return values


def normalize_name(value) -> str:
    text = _normalized(value).casefold().replace("&", " och ")
    return " ".join(re.findall(r"[^\W_]+", text, flags=re.UNICODE))


def _name_forms(value) -> set[str]:
    normalized = normalize_name(value)
    if not normalized:
        return set()
    forms = {normalized}
    words = normalized.split()
    while words and words[-1] in _COMPANY_SUFFIXES:
        words.pop()
    if words:
        forms.add(" ".join(words))
    return {form for form in forms if len(form) >= 4}


def _contains_name(normalized_text: str, value) -> bool:
    padded = f" {normalized_text} "
    return any(f" {form} " in padded for form in _name_forms(value))


def _logo_stem(value) -> str:
    # Stored values are filenames, but tolerate a legacy path with either slash.
    return Path(str(value or "").replace("\\", "/")).stem


def svg_logo_aliases(path) -> list[str]:
    """Return safe textual aliases from a logo filename and local SVG metadata."""
    path = Path(path)
    aliases = {_logo_stem(path.name)} if path.name else set()
    if path.is_file() and path.suffix.lower() == ".svg":
        try:
            root = ET.parse(path).getroot()
            for element in root.iter():
                tag = str(element.tag).rsplit("}", 1)[-1].casefold()
                if tag not in {"title", "text"}:
                    continue
                value = " ".join("".join(element.itertext()).split())
                if 3 <= len(value) <= 120:
                    aliases.add(value)
        except (OSError, ET.ParseError):
            pass
    return sorted(
        alias for alias in aliases
        if normalize_name(alias) and normalize_name(alias) not in _GENERIC_LOGO_NAMES
    )


def _safe_identifier(normalizer, value) -> str:
    try:
        return normalizer(value)
    except ValueError:
        return ""


def parse_supplier_identifier(field, text) -> str:
    """Parse a labelled or explicitly zoned organisation/bankgiro number."""

    if field == "org_number":
        normalizer, extractor, formatter = normalize_org_number, extract_org_numbers, format_org_number
    elif field == "bankgiro_number":
        normalizer, extractor, formatter = normalize_bankgiro_number, extract_bankgiro_numbers, format_bankgiro_number
    else:
        return ""
    values = extractor(text)
    try:
        if len(values) == 1:
            return formatter(next(iter(values)))
        # A hand-drawn zone may contain only the number without its label.
        return formatter(normalizer(text))
    except ValueError:
        return ""


def validate_supplier_logo_link(vendor, selected_logo, logo_files) -> str:
    """Require an explicit supplier before an existing logo is linked."""

    supplier = str(vendor or "").strip()
    selected = str(selected_logo or "")
    if selected in set(logo_files) and not supplier:
        raise ValueError("A supplier is required when linking a logo")
    return supplier


def match_supplier(text, profiles) -> SupplierMatch | None:
    """Return one match, ``None`` for no match or an empty-vendor ambiguity.

    Exact labelled identifiers are considered first. An identifier conflict is
    never resolved by a weaker name/logo match. Without an identifier match,
    normalized supplier names and textual logo aliases are compared. Ambiguity
    markers prevent callers from falling back to a less safe supplier guess.
    """
    org_numbers = extract_org_numbers(text)
    bankgiro_numbers = extract_bankgiro_numbers(text)
    exact = {}
    prepared = []
    for profile in profiles:
        vendor = str(profile.get("vendor") or "").strip()
        if not vendor:
            continue
        key = vendor.casefold()
        prepared.append((key, vendor, profile))
        entry = exact.setdefault(key, {"vendor": vendor, "org": False, "bg": False})
        stored_org = _safe_identifier(normalize_org_number, profile.get("org_number"))
        stored_bg = _safe_identifier(normalize_bankgiro_number, profile.get("bankgiro_number"))
        entry["org"] |= bool(stored_org and stored_org in org_numbers)
        entry["bg"] |= bool(stored_bg and stored_bg in bankgiro_numbers)

    exact_candidates = []
    for key, entry in exact.items():
        if not (entry["org"] or entry["bg"]):
            continue
        score = (1000 if entry["org"] else 0) + (800 if entry["bg"] else 0)
        methods = []
        if entry["org"]:
            methods.append("org_number")
        if entry["bg"]:
            methods.append("bankgiro_number")
        exact_candidates.append((score, key, entry["vendor"], "+".join(methods)))
    if exact_candidates:
        # Different vendors identified in the same invoice are a conflict, even
        # when one identifier type would otherwise have a higher score.
        if len(exact_candidates) != 1:
            return SupplierMatch("", "ambiguous_identifier", 0)
        score, _key, vendor, method = exact_candidates[0]
        return SupplierMatch(vendor, method, score)

    normalized_text = normalize_name(text)
    if not normalized_text:
        return None
    name_candidates = {}
    for key, vendor, profile in prepared:
        score = 0
        methods = []
        if _contains_name(normalized_text, vendor):
            score += 200
            methods.append("name")
        aliases = profile.get("aliases") or ()
        if isinstance(aliases, str):
            aliases = (aliases,)
        aliases = list(aliases)
        if profile.get("logo_file"):
            aliases.append(_logo_stem(profile.get("logo_file")))
        if any(_contains_name(normalized_text, alias) for alias in aliases):
            score += 120
            methods.append("logo")
        if not score:
            continue
        previous = name_candidates.get(key)
        candidate = SupplierMatch(vendor, "+".join(methods), score)
        if previous is None or score > previous.score:
            name_candidates[key] = candidate
        elif score == previous.score:
            merged = list(dict.fromkeys(previous.method.split("+") + methods))
            name_candidates[key] = SupplierMatch(previous.vendor, "+".join(merged), score)
    if not name_candidates:
        return None
    best_score = max(candidate.score for candidate in name_candidates.values())
    best = [candidate for candidate in name_candidates.values() if candidate.score == best_score]
    if len(best) != 1:
        return SupplierMatch("", "ambiguous_name", 0)
    return best[0]
