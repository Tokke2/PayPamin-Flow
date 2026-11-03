import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_database import load_headless_app

from supplier_matching import (
    extract_bankgiro_numbers,
    extract_org_numbers,
    format_bankgiro_number,
    format_org_number,
    match_supplier,
    normalize_bankgiro_number,
    normalize_org_number,
    svg_logo_aliases,
    validate_supplier_logo_link,
)


class SupplierIdentifierTests(unittest.TestCase):
    def test_normalizes_and_formats_swedish_identifiers(self):
        self.assertEqual(normalize_org_number(" 556123-4567 "), "5561234567")
        self.assertEqual(normalize_org_number("556123\u00a04567"), "5561234567")
        self.assertEqual(format_org_number("5561234567"), "556123-4567")
        self.assertEqual(normalize_bankgiro_number("123-4567"), "1234567")
        self.assertEqual(normalize_bankgiro_number("1234–5678"), "12345678")
        self.assertEqual(format_bankgiro_number("12345678"), "1234-5678")

    def test_rejects_invalid_identifiers(self):
        for value in ("556123-456", "556123-45678", "ABC5561234567"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_org_number(value)
        for value in ("12-3456", "12345-6789", "BG1234567"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_bankgiro_number(value)
        self.assertEqual(normalize_org_number(""), "")
        self.assertEqual(normalize_bankgiro_number(None), "")

    def test_extracts_only_explicitly_labelled_identifiers(self):
        text = (
            "Direktglas AB\nOrg.nr: 556123-4567\n"
            "Bankgiro 1234-5678\nKundens org.nr 559999-0001\n"
            "Bankgiro: 123-4567\nOrg-nr 556111-2222\nBG-nummer 555-1234\n"
            "Og mærkat 556111-2222\n"
        )
        self.assertEqual(extract_org_numbers(text), {"5561234567", "5599990001", "5561112222"})
        self.assertEqual(extract_bankgiro_numbers(text), {"12345678", "1234567", "5551234"})
        self.assertEqual(extract_org_numbers("556123-4567 utan etikett"), set())
        self.assertEqual(extract_bankgiro_numbers("1234-5678 utan etikett"), set())


class SupplierProfileMatchingTests(unittest.TestCase):
    def setUp(self):
        self.profiles = [
            {
                "vendor": "Direktglas AB",
                "logo_file": "direktglas.svg",
                "org_number": "5561234567",
                "bankgiro_number": "12345678",
            },
            {
                "vendor": "Martin G",
                "logo_file": "mg.svg",
                "org_number": "5599990001",
                "bankgiro_number": "9876543",
            },
        ]

    def test_org_number_beats_a_weaker_name_match(self):
        match = match_supplier(
            "Martin G\nFaktura\nOrg.nr 556123-4567",
            self.profiles,
        )
        self.assertEqual(match.vendor, "Direktglas AB")
        self.assertEqual(match.method, "org_number")

    def test_org_and_bankgiro_pointing_to_different_vendors_are_a_conflict(self):
        conflict = match_supplier(
            "Org.nr 556123-4567\nBankgiro: 987-6543",
            self.profiles,
        )
        self.assertEqual(conflict.vendor, "")
        self.assertEqual(conflict.method, "ambiguous_identifier")

    def test_bankgiro_matches_without_org_number(self):
        match = match_supplier("Faktura\nBG: 1234-5678", self.profiles)
        self.assertEqual(match.vendor, "Direktglas AB")
        self.assertEqual(match.method, "bankgiro_number")

    def test_both_identifiers_make_one_stronger_match(self):
        match = match_supplier(
            "Org.nr 556123-4567\nBankgiro 1234-5678",
            self.profiles,
        )
        self.assertEqual(match.vendor, "Direktglas AB")
        self.assertEqual(match.method, "org_number+bankgiro_number")
        self.assertEqual(match.score, 1800)

    def test_conflicting_equal_identifier_matches_are_not_guessed(self):
        profiles = [dict(self.profiles[0]), dict(self.profiles[1])]
        profiles[1]["org_number"] = profiles[0]["org_number"]
        conflict = match_supplier("Org.nr 556123-4567\nDirektglas AB", profiles)
        self.assertEqual(conflict.vendor, "")
        self.assertEqual(conflict.method, "ambiguous_identifier")

    def test_name_match_ignores_company_suffix_and_short_logo_alias(self):
        match = match_supplier("Faktura från Direktglas\nATT BETALA 100 SEK", self.profiles)
        self.assertEqual(match.vendor, "Direktglas AB")
        self.assertEqual(match.method, "name+logo")
        self.assertIsNone(match_supplier("MG\nFaktura 100 SEK", self.profiles))

    def test_logo_filename_is_a_fallback_alias(self):
        profiles = [{"vendor": "Annat namn AB", "logo_file": "Nordisk-Glas.svg"}]
        match = match_supplier("Nordisk Glas\nFaktura 42", profiles)
        self.assertEqual(match.vendor, "Annat namn AB")
        self.assertEqual(match.method, "logo")

    def test_linking_an_existing_logo_requires_an_explicit_supplier(self):
        for vendor in ("", "   "):
            with self.subTest(vendor=vendor), self.assertRaises(ValueError):
                validate_supplier_logo_link(vendor, "nordic.svg", ["nordic.svg"])
        self.assertEqual(
            validate_supplier_logo_link("  Nordic AB  ", "nordic.svg", ["nordic.svg"]),
            "Nordic AB",
        )
        self.assertEqual(validate_supplier_logo_link("", "(Välj logotyp)", ["nordic.svg"]), "")
        self.assertEqual(validate_supplier_logo_link("", "", []), "")

    def test_equal_name_matches_are_not_guessed(self):
        profiles = [
            {"vendor": "Direktglas AB", "logo_file": "one.svg"},
            {"vendor": "Direktglas HB", "logo_file": "two.svg"},
        ]
        conflict = match_supplier("Direktglas\nFaktura", profiles)
        self.assertEqual(conflict.vendor, "")
        self.assertEqual(conflict.method, "ambiguous_name")

    def test_svg_title_and_text_supply_logo_aliases(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "generic.svg"
            path.write_text(
                "<svg xmlns='http://www.w3.org/2000/svg'>"
                "<title>Nordisk Glas</title><text>Glasgruppen</text></svg>",
                encoding="utf-8",
            )
            self.assertEqual(svg_logo_aliases(path), ["Glasgruppen", "Nordisk Glas", "generic"])
            profiles = [{
                "vendor": "Annat namn AB",
                "logo_file": path.name,
                "aliases": svg_logo_aliases(path),
            }]
            match = match_supplier("Glasgruppen\nFaktura", profiles)
            self.assertEqual(match.method, "logo")

    def test_broken_svg_keeps_filename_alias(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "direktglas.svg"
            path.write_text("<svg>", encoding="utf-8")
            self.assertEqual(svg_logo_aliases(path), ["direktglas"])


class SupplierAppIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "supplier.sqlite3"
        self.app.SVG_DIR = self.workspace / "svg"
        self.app.SVG_DIR.mkdir(exist_ok=True)
        self.app.init_db()

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def guess(self, text):
        return self.app.ReminderApp.guess_supplier(SimpleNamespace(), text)

    def test_real_app_uses_saved_identifiers_and_logo_aliases(self):
        with self.app.connect() as db:
            db.execute(
                "INSERT INTO vendor_logos(vendor,logo_file,org_number,bankgiro_number) VALUES(?,?,?,?)",
                ("Annat Namn AB", "nordisk-glas.svg", "5561234567", "12345678"),
            )
        self.assertEqual(self.guess("Org.nr: 556123-4567"), "Annat Namn AB")
        self.assertEqual(self.guess("Bankgiro 1234-5678"), "Annat Namn AB")
        self.assertEqual(self.guess("Nordisk Glas\nFaktura"), "Annat Namn AB")

    def test_legacy_zone_only_template_is_still_matchable(self):
        with self.app.connect() as db:
            db.execute(
                "INSERT INTO pdf_zones(vendor,field,page_index,x0,y0,x1,y1,samples) VALUES(?,?,?,?,?,?,?,?)",
                ("Zon Utan Logotyp AB", "amount", 0, 0.1, 0.2, 0.3, 0.4, 1),
            )
        self.assertEqual(self.guess("Zon Utan Logotyp\nFaktura"), "Zon Utan Logotyp AB")

    def test_real_app_does_not_use_legacy_guess_after_identifier_conflict(self):
        with self.app.connect() as db:
            db.execute(
                "INSERT INTO vendor_logos(vendor,logo_file,org_number,bankgiro_number) VALUES(?,?,?,?)",
                ("Direktglas AB", "one.svg", "5561234567", ""),
            )
            db.execute(
                "INSERT INTO vendor_logos(vendor,logo_file,org_number,bankgiro_number) VALUES(?,?,?,?)",
                ("Martin G", "two.svg", "5561234567", ""),
            )
        self.assertEqual(self.guess("Direktglas AB\nOrg.nr 556123-4567"), "")

    def test_failed_supplier_match_is_logged_for_manual_review(self):
        with patch.object(self.app.logger, "warning") as warning:
            self.assertEqual(self.guess("Faktura utan känd leverantör"), "")
        messages = [call.args[0] for call in warning.call_args_list]
        self.assertTrue(any("manual review required" in message for message in messages))

    def test_legacy_company_name_guess_remains_when_no_profile_matches(self):
        self.assertEqual(self.guess("Faktura\nSnickeriet AB\nATT BETALA 100 SEK"), "Snickeriet AB")


if __name__ == "__main__":
    unittest.main()
