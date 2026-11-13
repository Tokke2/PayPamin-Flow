import unittest

import fee_rules
from fee_rules import (
    AGREEMENT_CONTRACT, AGREEMENT_INVOICE, AGREEMENT_NONE,
    CUSTOMER_AUTHORITY, CUSTOMER_BUSINESS, CUSTOMER_PRIVATE,
    LATE_PAYMENT_COMPENSATION, REMINDER_FEE_CAP,
    assess_fee, cap_for, chargeable_fee, default_fee, fee_kind, is_business,
    normalize_agreement, normalize_customer_type,
)


class FeeRuleTests(unittest.TestCase):
    """The amounts come from lag (1981:739) 4 §, 4 a § and 5 § 2 st."""

    def test_reminder_fee_is_capped_at_sixty_kronor(self):
        self.assertEqual(REMINDER_FEE_CAP, 60.0)
        self.assertFalse(assess_fee(CUSTOMER_PRIVATE, 60).blocked)
        self.assertTrue(assess_fee(CUSTOMER_PRIVATE, 150).blocked)
        self.assertEqual(chargeable_fee(CUSTOMER_PRIVATE, 150), 60.0)

    def test_a_higher_agreed_amount_is_still_refused(self):
        """6 § makes a wider term void, so an agreement cannot raise the cap."""
        self.assertTrue(assess_fee(CUSTOMER_PRIVATE, 150, agreement=AGREEMENT_CONTRACT).blocked)

    def test_business_gets_forty_five_percent_compensation(self):
        self.assertEqual(LATE_PAYMENT_COMPENSATION, 450.0)
        self.assertEqual(fee_kind(CUSTOMER_BUSINESS, 450), fee_rules.KIND_COMPENSATION)
        self.assertEqual(cap_for(CUSTOMER_BUSINESS, 450), 450.0)
        self.assertFalse(assess_fee(CUSTOMER_BUSINESS, 450).blocked)

    def test_business_below_compensation_becomes_a_reminder_fee(self):
        """Without agreement a business may still only be charged 60 kr."""
        self.assertEqual(fee_kind(CUSTOMER_BUSINESS, 60), fee_rules.KIND_REMINDER_FEE)
        self.assertTrue(assess_fee(CUSTOMER_BUSINESS, 150).blocked)
        self.assertTrue(assess_fee(CUSTOMER_BUSINESS, 500).blocked)

    def test_authority_is_treated_as_business_but_zero_fee_is_allowed(self):
        self.assertTrue(is_business(CUSTOMER_AUTHORITY))
        self.assertEqual(default_fee(CUSTOMER_AUTHORITY), 450.0)
        self.assertFalse(assess_fee(CUSTOMER_AUTHORITY, 0).blocked)
        self.assertEqual(assess_fee(CUSTOMER_AUTHORITY, 0).issues, ())

    def test_unknown_customer_type_falls_back_to_consumer(self):
        self.assertEqual(normalize_customer_type(""), CUSTOMER_PRIVATE)
        self.assertEqual(normalize_customer_type("company"), CUSTOMER_PRIVATE)
        self.assertEqual(normalize_customer_type(" BUSINESS "), CUSTOMER_BUSINESS)
        self.assertEqual(normalize_agreement("nonsense"), AGREEMENT_NONE)

    def test_missing_agreement_is_a_warning_not_a_block(self):
        assessment = assess_fee(CUSTOMER_PRIVATE, 60)
        self.assertFalse(assessment.blocked)
        self.assertEqual(len(assessment.warnings), 1)
        self.assertIn("avtal", assessment.warnings[0].key)

    def test_agreement_printed_only_on_the_invoice_is_reported(self):
        assessment = assess_fee(CUSTOMER_PRIVATE, 60, agreement=AGREEMENT_INVOICE)
        self.assertEqual(len(assessment.warnings), 1)
        self.assertIn("fakturan", assessment.warnings[0].key)
        self.assertEqual(assess_fee(CUSTOMER_PRIVATE, 60, agreement=AGREEMENT_CONTRACT).issues, ())

    def test_non_sek_invoice_cannot_be_verified_automatically(self):
        assessment = assess_fee(CUSTOMER_PRIVATE, 60, currency="EUR", agreement=AGREEMENT_CONTRACT)
        self.assertFalse(assessment.blocked)
        self.assertEqual(len(assessment.warnings), 1)
        self.assertIn("SEK", assessment.warnings[0].key)
        self.assertEqual(assessment.warnings[0].values, (("currency", "EUR"),))

    def test_negative_fee_can_never_be_charged(self):
        self.assertTrue(assess_fee(CUSTOMER_PRIVATE, -10).blocked)
        self.assertEqual(chargeable_fee(CUSTOMER_PRIVATE, -10), 0.0)

    def test_bad_input_is_read_as_zero(self):
        self.assertEqual(chargeable_fee(CUSTOMER_PRIVATE, "not a number"), 0.0)
        self.assertFalse(assess_fee(CUSTOMER_PRIVATE, None).blocked)

    def test_labels_follow_the_amount(self):
        self.assertEqual(fee_rules.fee_label_key(CUSTOMER_PRIVATE, 60), "Påminnelseavgift")
        self.assertEqual(fee_rules.fee_label_key(CUSTOMER_BUSINESS, 450), "Förseningsersättning")
        self.assertIn("4 a §", fee_rules.legal_basis_key(CUSTOMER_BUSINESS, 450))
        self.assertIn("4 §", fee_rules.legal_basis_key(CUSTOMER_PRIVATE, 60))


if __name__ == "__main__":
    unittest.main()
