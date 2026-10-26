import unittest

from currency import find_currency_code, is_valid_currency, normalize_currency
from i18n import format_money, set_language


class CurrencyTests(unittest.TestCase):
    def tearDown(self):
        set_language("sv")

    def test_normalizes_three_letter_codes_and_defaults_to_sek(self):
        self.assertEqual(normalize_currency(" eur "), "EUR")
        self.assertEqual(normalize_currency("usd"), "USD")
        self.assertEqual(normalize_currency(""), "SEK")
        self.assertEqual(normalize_currency("not-a-code"), "SEK")
        self.assertTrue(is_valid_currency("NOK"))
        self.assertFalse(is_valid_currency("NO"))
        self.assertFalse(is_valid_currency("EURO"))

    def test_detects_only_explicit_currency_codes(self):
        self.assertEqual(find_currency_code("ATT BETALA 1 234,50 EUR"), "EUR")
        self.assertEqual(find_currency_code("6 563,00 sek"), "SEK")
        self.assertEqual(find_currency_code("nok"), "NOK")
        self.assertEqual(find_currency_code("Ingen valuta angiven"), "")

    def test_other_currencies_use_swedish_number_format(self):
        self.assertEqual(format_money(1234.5, "EUR"), "1 234,50 EUR")
        self.assertEqual(format_money(1234.5, "nok"), "1 234,50 NOK")

    def test_other_currencies_use_english_number_format(self):
        set_language("en")
        self.assertEqual(format_money(1234.5, "USD"), "USD 1,234.50")
        self.assertEqual(format_money(1234.5, "dkk"), "DKK 1,234.50")

    def test_sek_format_and_invalid_currency_fallback_are_backward_compatible(self):
        self.assertEqual(format_money(6563), "6 563,00 kr")
        self.assertEqual(format_money(6563, "invalid"), "6 563,00 kr")
        set_language("en")
        self.assertEqual(format_money(6563), "SEK 6,563.00")


if __name__ == "__main__":
    unittest.main()
