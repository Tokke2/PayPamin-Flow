import sys
import types
import unittest
from unittest.mock import patch

from invoice_parser import extract_invoice_sections, normalize_amount, parse_invoice_text, split_invoice_pages


class InvoiceParserTests(unittest.TestCase):
    def test_uses_att_betala_gross_total_not_ex_vat_subtotal(self):
        text = """Fakturabelopp exkl moms\n5 250,00\nMoms 25 %\n1 312,50\nTotal exkl moms 5 250,00\nATT BETALA\n6 563,00 SEK"""
        self.assertEqual(parse_invoice_text(text)["amount"], 6563.0)

    def test_extracts_customer_from_street_address_block(self):
        text = """TADEGA AB\nFaktura\nLeveransadress\nProtector Försäkring\nSkador FE 50340\n832 82 Frösön\nProtector Försäkring ASA\nVästra Trädgårdsgatan 15\n111 53 Stockholm\nKundnr 841630700\nEr referens Mikael Lütz"""
        self.assertEqual(parse_invoice_text(text)["customer"], "Protector Försäkring ASA")

    def test_extracts_invoice_and_due_dates_and_description(self):
        text = """Fakturanummer 6258\nFakturadatum 2026-09-03\nFörfallodatum 2026-10-03\nATT BETALA 6 563,00 SEK\nArtikel Benämning Enhet Antal Summa\nHandelskammartjänst enligt ovan\nExkl moms 5 250,00"""
        parsed = parse_invoice_text(text)
        self.assertEqual(parsed["invoice_no"], "6258")
        self.assertEqual(parsed["invoice_date"], "2026-09-03")
        self.assertEqual(parsed["due_date"], "2026-10-03")
        self.assertEqual(parsed["note"], "Handelskammartjänst enligt ovan")

    def test_does_not_guess_net_subtotal_as_amount_when_payable_total_missing(self):
        text = "Total exkl moms 5 250,00\nMoms 1 312,50"
        self.assertEqual(parse_invoice_text(text)["amount"], 0.0)

    def test_detects_currency_next_to_payable_total(self):
        text = "Fakturanummer 7001\nATT BETALA\n1 234,50 EUR"
        parsed = parse_invoice_text(text)
        self.assertEqual(parsed["amount"], 1234.5)
        self.assertEqual(parsed["currency"], "EUR")

    def test_detects_explicit_currency_label(self):
        text = "Valuta: USD\nFakturanummer 7002\nATT BETALA 250,00"
        self.assertEqual(parse_invoice_text(text)["currency"], "USD")

    def test_normalizes_swedish_european_and_english_amount_formats(self):
        cases = {
            "12,50": 12.5,
            "12.50": 12.5,
            "1250.50": 1250.5,
            "1 234,56": 1234.56,
            "1.234,56": 1234.56,
            "1,234.56": 1234.56,
            "1,234": 1234.0,
            "1.234": 1234.0,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_amount(raw), expected)

    def test_reads_english_total_due_and_us_amount(self):
        text = """Invoice # INV-2045\nInvoice date: 2026-10-01\nDue date: 2026-10-15\nCurrency: GBP\nTotal due\n1,234.56\nDescription\nConsulting services"""
        parsed = parse_invoice_text(text)
        self.assertEqual(parsed["invoice_no"], "INV-2045")
        self.assertEqual(parsed["invoice_date"], "2026-10-01")
        self.assertEqual(parsed["due_date"], "2026-10-15")
        self.assertEqual(parsed["amount"], 1234.56)
        self.assertEqual(parsed["currency"], "GBP")
        self.assertEqual(parsed["note"], "Consulting services")

    def test_reads_amount_due_with_european_decimal(self):
        parsed = parse_invoice_text("Amount due: EUR 950,75")
        self.assertEqual(parsed["amount"], 950.75)
        self.assertEqual(parsed["currency"], "EUR")

    def test_reads_amount_before_payable_label_and_currency(self):
        parsed = parse_invoice_text("GBP 1,234.56 Total due")
        self.assertEqual(parsed["amount"], 1234.56)
        self.assertEqual(parsed["currency"], "GBP")

    def test_payable_amount_does_not_pick_invoice_number_or_date(self):
        parsed = parse_invoice_text("ATT BETALA\nFakturanummer 6258\n2026-10-31\n6 563,00 SEK")
        self.assertEqual(parsed["amount"], 6563.0)

    def test_invoice_hash_label_between_total_and_amount_is_skipped(self):
        parsed = parse_invoice_text("Total due\nInvoice # 2045\n1,234.56")
        self.assertEqual(parsed["invoice_no"], "2045")
        self.assertEqual(parsed["amount"], 1234.56)

    def test_payable_label_does_not_turn_vat_into_total(self):
        parsed = parse_invoice_text("ATT BETALA\nMoms 25 %\n1 312,50\nTotal exkl moms 5 250,00")
        self.assertEqual(parsed["amount"], 0.0)

    def test_grand_total_fallback_is_supported(self):
        parsed = parse_invoice_text("Grand total USD 800.25")
        self.assertEqual(parsed["amount"], 800.25)
        self.assertEqual(parsed["currency"], "USD")

    def test_zero_payable_total_does_not_fall_back_to_subtotal(self):
        parsed = parse_invoice_text("ATT BETALA 0,00 SEK\nTotal exkl moms 100,00")
        self.assertEqual(parsed["amount"], 0.0)

    def test_unique_euro_symbol_near_total_is_detected(self):
        parsed = parse_invoice_text("Total due € 1.234,56")
        self.assertEqual(parsed["amount"], 1234.56)
        self.assertEqual(parsed["currency"], "EUR")

    def test_payable_whole_amount_without_decimals(self):
        parsed = parse_invoice_text("ATT BETALA 6 563 SEK")
        self.assertEqual(parsed["amount"], 6563.0)

    def test_defaults_to_sek_when_no_currency_is_detectable(self):
        text = "Fakturanummer 7003\nATT BETALA 6 563,00"
        self.assertEqual(parse_invoice_text(text)["currency"], "SEK")


class MultiInvoicePdfTests(unittest.TestCase):
    def test_two_single_page_invoices_are_split(self):
        sections = split_invoice_pages([
            "Fakturanummer 8001\nFörfallodatum 2026-11-01\nATT BETALA 100,00 SEK",
            "Fakturanummer 8002\nFörfallodatum 2026-11-02\nATT BETALA 200,00 SEK",
        ])
        self.assertEqual([section.page_indexes for section in sections], [(0,), (1,)])
        self.assertEqual([parse_invoice_text(section.text)["amount"] for section in sections], [100.0, 200.0])

    def test_continuation_pages_stay_with_their_invoice(self):
        sections = split_invoice_pages([
            "Fakturanummer 8101\nFakturadatum 2026-10-01\nBeskrivning\nFörsta sidans arbete",
            "Fakturanummer 8101\nFortsättning\nBeskrivning\nAndra sidans arbete\nATT BETALA 300,00 SEK",
            "Fakturanummer 8102\nFörfallodatum 2026-11-15\nATT BETALA 450,00 SEK",
        ])
        self.assertEqual([section.page_indexes for section in sections], [(0, 1), (2,)])
        first = parse_invoice_text(sections[0].text)
        self.assertEqual(first["invoice_no"], "8101")
        self.assertEqual(first["amount"], 300.0)
        self.assertIn("Andra sidans arbete", sections[0].text)

    def test_page_without_repeated_number_is_a_continuation(self):
        sections = split_invoice_pages([
            "Fakturanummer 8201\nBeskrivning\nFörsta sidan",
            "Specifikation fortsättning\nBeskrivning\nAndra sidan\nATT BETALA 500,00 SEK",
            "Fakturanummer 8202\nATT BETALA 600,00 SEK",
        ])
        self.assertEqual([section.page_indexes for section in sections], [(0, 1), (2,)])

    def test_pdf_extraction_keeps_page_boundaries_and_closes_document(self):
        page_texts = [
            "Fakturanummer 8301\nATT BETALA 700,00 SEK",
            "Fakturanummer 8302\nATT BETALA 800,00 SEK",
        ]

        class FakePage:
            def __init__(self, text):
                self.text = text

            def get_text(self, mode):
                self.mode = mode
                return self.text

        class FakeDocument:
            def __init__(self):
                self.pages = [FakePage(text) for text in page_texts]
                self.closed = False

            def __iter__(self):
                return iter(self.pages)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.closed = True

        document = FakeDocument()
        fake_fitz = types.ModuleType("fitz")
        fake_fitz.open = lambda path: document
        with patch.dict(sys.modules, {"fitz": fake_fitz}):
            sections = extract_invoice_sections("bundled.pdf")
        self.assertTrue(document.closed)
        self.assertEqual([section.page_indexes for section in sections], [(0,), (1,)])
        self.assertEqual([parse_invoice_text(section.text)["invoice_no"] for section in sections], ["8301", "8302"])


if __name__ == "__main__":
    unittest.main()
