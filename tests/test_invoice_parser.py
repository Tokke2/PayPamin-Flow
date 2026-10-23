import unittest

from paypaminn_flow import parse_invoice_text


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


if __name__ == "__main__":
    unittest.main()
