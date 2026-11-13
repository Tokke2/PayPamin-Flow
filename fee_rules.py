"""Swedish late-payment fee rules for PayPamin Flow.

The amounts come from lag (1981:739) om ersättning för inkassokostnader m.m.:

* **4 § 1** – a written reminder may be charged at most **60 kr**, and only
  "om det inte finns särskilda skäl till annat".
* **4 a §** – between businesses, and towards authorities, a late-payment
  compensation of **450 kr** is due without any prior agreement.
* **5 § 2 st** – the compensation consumes the right to a reminder fee: the
  other fees may only be charged for the part that exceeds 450 kr.
* **6 §** – a contract term that widens the debtor's liability beyond the law
  is **void**, so a higher amount cannot be agreed either.

Two consequences shape this module:

1. The app charges **one fee per claim**, never one per reminder letter. P2
   therefore never adds a second fee on top of P1.
2. A reminder fee requires an agreement made **no later than when the debt
   arose** (2 §). A condition printed only on the overdue invoice is normally
   too late, so that case is reported instead of being treated as valid.

Two **fee models** are selectable, and both amounts are fixed — the app never
lets anyone type a number:

* ``statutory`` – the amounts above: 60 kr to a consumer, 450 kr to a business.
* ``per_reminder`` – a flat **150 kr** per reminder, as stated in the invoice
  terms. Against a business that is below the 450 kr right in 4 a § and lawful.
  Against a **consumer it is above the 60 kr cap in 4 §**, and 6 § makes a
  wider term void, so the amount cannot be enforced there. The app therefore
  warns on every consumer reminder instead of pretending it is lawful, and the
  statutory model stays one click away.

Every amount is in SEK. The law sets the cap in kronor, so an invoice in
another currency cannot be verified automatically; it is reported as
unverified rather than converted at a guessed rate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CUSTOMER_PRIVATE = "private"
CUSTOMER_BUSINESS = "business"
CUSTOMER_AUTHORITY = "authority"
CUSTOMER_TYPES = (CUSTOMER_PRIVATE, CUSTOMER_BUSINESS, CUSTOMER_AUTHORITY)

# 4 § 1 and 4 a § of lag (1981:739). These are the amounts of the statutory
# model, and they are intentionally not configurable.
REMINDER_FEE_CAP = 60.0
LATE_PAYMENT_COMPENSATION = 450.0

# The fee models. ``per_reminder`` charges one flat amount, the one printed in
# the invoice terms; ``statutory`` follows 4 § and 4 a §. Neither amount can be
# edited — the choice is between two fixed models, never a free number.
FEE_MODEL_PER_REMINDER = "per_reminder"
FEE_MODEL_STATUTORY = "statutory"
FEE_MODELS = (FEE_MODEL_PER_REMINDER, FEE_MODEL_STATUTORY)
DEFAULT_FEE_MODEL = FEE_MODEL_PER_REMINDER
PER_REMINDER_FEE = 150.0

KIND_REMINDER_FEE = "reminder_fee"
KIND_COMPENSATION = "compensation"

SEK = "SEK"

AGREEMENT_NONE = ""
AGREEMENT_CONTRACT = "contract"
AGREEMENT_OFFER = "offer"
AGREEMENT_INVOICE = "invoice"
AGREEMENTS = (AGREEMENT_CONTRACT, AGREEMENT_OFFER, AGREEMENT_INVOICE)

#: Tolerance for float comparisons of money amounts.
MONEY_EPSILON = 0.005

# Issue levels. ``error`` means the amount is not lawful; ``warning`` means it
# may be lawful but the app cannot confirm it and the user must decide.
LEVEL_ERROR = "error"
LEVEL_WARNING = "warning"


@dataclass(frozen=True)
class FeeIssue:
    """One thing the user has to know before charging the fee."""

    level: str
    key: str
    values: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class FeeAssessment:
    """The result of checking one fee against the law."""

    customer_type: str
    fee: float
    kind: str
    cap: float
    issues: tuple = field(default_factory=tuple)

    @property
    def blocked(self) -> bool:
        """True when the amount may not be charged as it stands."""
        return any(issue.level == LEVEL_ERROR for issue in self.issues)

    @property
    def warnings(self) -> tuple:
        return tuple(issue for issue in self.issues if issue.level == LEVEL_WARNING)

    @property
    def problems(self) -> tuple:
        return tuple(issue for issue in self.issues if issue.level == LEVEL_ERROR)


def normalize_customer_type(value) -> str:
    """Return a known customer type, defaulting to a consumer.

    A consumer is the safe default because 60 kr is lawful in every
    relationship, while 450 kr is not.
    """
    text = str(value or "").strip().lower()
    return text if text in CUSTOMER_TYPES else CUSTOMER_PRIVATE


def is_business(customer_type) -> bool:
    """True for businesses and authorities, which may be charged 4 a §."""
    return normalize_customer_type(customer_type) in (CUSTOMER_BUSINESS, CUSTOMER_AUTHORITY)


def normalize_fee_model(value) -> str:
    """Return a known fee model, defaulting to the per-reminder model."""
    text = str(value or "").strip().lower()
    return text if text in FEE_MODELS else DEFAULT_FEE_MODEL


def fee_for_model(model, customer_type) -> float:
    """Return the fixed amount this model charges for this customer type."""
    if normalize_fee_model(model) == FEE_MODEL_PER_REMINDER:
        return PER_REMINDER_FEE
    return LATE_PAYMENT_COMPENSATION if is_business(customer_type) else REMINDER_FEE_CAP


def normalize_agreement(value) -> str:
    """Return a known agreement location, or an empty string."""
    text = str(value or "").strip().lower()
    return text if text in AGREEMENTS else AGREEMENT_NONE


def fee_kind(customer_type, fee, model=FEE_MODEL_STATUTORY) -> str:
    """Return what the amount is, judged by the model and the customer type.

    In the per-reminder model the amount is always a reminder fee, never the
    450 kr compensation. In the statutory model a business customer charged the
    full 450 kr is getting late-payment compensation, while anything lower -
    including 0 - is a reminder fee.
    """
    if normalize_fee_model(model) == FEE_MODEL_PER_REMINDER:
        return KIND_REMINDER_FEE
    amount = _amount(fee)
    if is_business(customer_type) and amount >= LATE_PAYMENT_COMPENSATION - MONEY_EPSILON:
        return KIND_COMPENSATION
    return KIND_REMINDER_FEE


def cap_for(customer_type, fee=None, model=FEE_MODEL_STATUTORY) -> float:
    """Return the highest amount this model allows for this customer."""
    if normalize_fee_model(model) == FEE_MODEL_PER_REMINDER:
        return PER_REMINDER_FEE
    if fee_kind(customer_type, fee, model) == KIND_COMPENSATION:
        return LATE_PAYMENT_COMPENSATION
    return REMINDER_FEE_CAP


def default_fee(customer_type, model=FEE_MODEL_STATUTORY) -> float:
    """Return the amount a model suggests for this customer type.

    The default here is the statutory model, because that is the amount the law
    itself sets; the app decides separately which model is selected.
    """
    return fee_for_model(model, customer_type)


def needs_agreement(customer_type, fee, model=FEE_MODEL_STATUTORY) -> bool:
    """True when the amount is a reminder fee that must be agreed in advance."""
    return fee_kind(customer_type, fee, model) == KIND_REMINDER_FEE


def fee_label_key(customer_type, fee, model=FEE_MODEL_STATUTORY) -> str:
    """Return the translation key for the fee line on the reminder."""
    if normalize_fee_model(model) == FEE_MODEL_PER_REMINDER:
        return "Avgift per påminnelse"
    if fee_kind(customer_type, fee, model) == KIND_COMPENSATION:
        return "Förseningsersättning"
    return "Påminnelseavgift"


def legal_basis_key(customer_type, fee, model=FEE_MODEL_STATUTORY) -> str:
    """Return the translation key naming the ground the amount rests on."""
    if normalize_fee_model(model) == FEE_MODEL_PER_REMINDER:
        return "Avgift per påminnelse enligt avtal, 150 kr."
    if fee_kind(customer_type, fee, model) == KIND_COMPENSATION:
        return "Förseningsersättning enligt 4 a § lagen (1981:739)."
    return "Påminnelseavgift enligt 4 § lagen (1981:739), högst 60 kr."


def chargeable_fee(customer_type, fee, model=FEE_MODEL_STATUTORY) -> float:
    """Return the amount actually charged for one claim.

    The fee is charged once per claim. There is no second fee for a second
    reminder, and a negative amount is never charged.
    """
    amount = _amount(fee)
    return max(0.0, min(amount, cap_for(customer_type, amount, model)))


def assess_fee(customer_type, fee, currency=SEK, agreement=AGREEMENT_NONE, model=FEE_MODEL_STATUTORY) -> FeeAssessment:
    """Check one fee against the law and report what the user must decide."""
    ctype = normalize_customer_type(customer_type)
    chosen = normalize_fee_model(model)
    amount = _amount(fee)
    kind = fee_kind(ctype, amount, chosen)
    limit = cap_for(ctype, amount, chosen)
    issues: list[FeeIssue] = []

    if amount < 0:
        issues.append(FeeIssue(LEVEL_ERROR, "Avgiften kan inte vara negativ."))
        amount = 0.0
    elif amount > limit + MONEY_EPSILON:
        issues.append(FeeIssue(
            LEVEL_ERROR,
            "Avgiften {fee} är högre än det lagliga taket {cap} för {customer}.",
            (("fee", _money(amount)), ("cap", _money(limit)), ("customer", ctype)),
        ))

    if chosen == FEE_MODEL_PER_REMINDER:
        if amount > 0 and not is_business(ctype) and amount > REMINDER_FEE_CAP + MONEY_EPSILON:
            # A warning, not a block: the operator has explicitly chosen this
            # model, but the amount still cannot be enforced against a consumer.
            issues.append(FeeIssue(
                LEVEL_WARNING,
                "Avgiften {fee} är högre än taket {cap} i 4 §. Mot en privatperson kan beloppet inte krävas in; välj den lagstadgade avgiften för privatpersoner.",
                (("fee", _money(amount)), ("cap", _money(REMINDER_FEE_CAP))),
            ))
    elif amount > 0 and needs_agreement(ctype, amount, chosen):
        location = normalize_agreement(agreement)
        if not location:
            issues.append(FeeIssue(
                LEVEL_WARNING,
                "Påminnelseavgiften kräver att rätten till den avtalades senast när skulden uppstod.",
            ))
        elif location == AGREEMENT_INVOICE:
            issues.append(FeeIssue(
                LEVEL_WARNING,
                "Villkoret står bara på fakturan. Det är oftast för sent, eftersom skulden uppstod innan fakturan skrevs.",
            ))

    if amount > 0 and str(currency or SEK).strip().upper() != SEK:
        issues.append(FeeIssue(
            LEVEL_WARNING,
            "Taket gäller i SEK. Fakturan är i {currency}, så kontrollera beloppet mot växelkursen.",
            (("currency", str(currency or "").strip().upper()),),
        ))

    return FeeAssessment(customer_type=ctype, fee=amount, kind=kind, cap=limit, issues=tuple(issues))


def _money(value: float) -> str:
    """Format a fee amount for a message without trailing zeros."""
    return f"{value:g}"


def _amount(value) -> float:
    """Read a money amount without ever raising on bad input."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
