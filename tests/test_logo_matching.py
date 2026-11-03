import io
import tempfile
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import patch

import fitz
from PIL import Image, ImageChops
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg

from logo_matching import match_pdf_logo
from test_database import load_headless_app


NORDIC_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="240" height="90">
<rect x="3" y="8" width="62" height="62" rx="12" fill="#165a9f"/>
<path d="M18 50 L32 25 L49 50 Z" fill="white"/>
<text x="78" y="52" font-family="Helvetica" font-size="31" font-weight="bold" fill="#18324b">NORDIC</text>
</svg>"""
OTHER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="240" height="90">
<circle cx="40" cy="40" r="31" fill="#ba3434"/>
<path d="M20 40 L60 40 M40 20 L40 60" stroke="white" stroke-width="8"/>
<text x="82" y="50" font-family="Helvetica" font-size="29" font-weight="bold" fill="#572222">OTHER</text>
</svg>"""


def write_svg(path, content):
    path.write_text(content, encoding="utf-8")
    drawing = svg2rlg(str(path))
    pdf = renderPDF.drawToString(drawing)
    with fitz.open("pdf", pdf) as document:
        pixmap = document[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    image = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")
    bbox = ImageChops.difference(image, Image.new("RGB", image.size, "white")).getbbox()
    if bbox:
        image = image.crop(bbox)
    png = path.with_suffix(".png")
    image.save(png)
    return png


def write_invoice(path, logo_png, rectangle):
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(*rectangle), filename=str(logo_png), keep_proportion=False)
    page.insert_text((48, 190), "Faktura 9750275738", fontsize=16)
    page.insert_text((48, 220), "Kund och betalningsinformation", fontsize=11)
    for index in range(15):
        page.insert_text((48, 270 + index * 24), f"Rad {index}  123456789  1 250,00 SEK", fontsize=9)
    document.save(path)
    document.close()


def write_vector_invoice(path, svg_path, rectangle):
    drawing = svg2rlg(str(svg_path))
    logo_pdf = renderPDF.drawToString(drawing)
    source = fitz.open("pdf", logo_pdf)
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.show_pdf_page(fitz.Rect(*rectangle), source, 0, keep_proportion=False)
    page.insert_text((48, 190), "Faktura med vektorlogotyp", fontsize=16)
    document.save(path)
    document.close()
    source.close()


class VisualLogoMatchingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.nordic = self.root / "nordic.svg"
        self.other = self.root / "other.svg"
        self.nordic_png = write_svg(self.nordic, NORDIC_SVG)
        self.other_png = write_svg(self.other, OTHER_SVG)
        self.invoice = self.root / "invoice.pdf"
        write_invoice(self.invoice, self.nordic_png, (355, 42, 535, 99))
        self.profiles = [
            {"vendor": "Nordic AB", "logo_file": self.nordic.name},
            {"vendor": "Other AB", "logo_file": self.other.name},
        ]
        self.addCleanup(self.temporary.cleanup)

    def test_same_svg_logo_is_recognized_in_pdf(self):
        match = match_pdf_logo(self.invoice, [0], self.profiles, self.root)
        self.assertIsNotNone(match)
        self.assertEqual(match.vendor, "Nordic AB")
        self.assertEqual(match.method, "visual_logo")
        self.assertGreater(match.score, 0)

    def test_vector_svg_logo_is_recognized_without_a_raster_image(self):
        vector_invoice = self.root / "vector.pdf"
        write_vector_invoice(vector_invoice, self.nordic, (355, 42, 535, 99))
        match = match_pdf_logo(vector_invoice, [0], self.profiles, self.root)
        self.assertIsNotNone(match)
        self.assertEqual(match.vendor, "Nordic AB")

    def test_pdf_filename_is_not_used_for_visual_match(self):
        renamed = self.root / "not-a-supplier-name.pdf"
        self.invoice.rename(renamed)
        match = match_pdf_logo(renamed, [0], self.profiles, self.root)
        self.assertIsNotNone(match)
        self.assertEqual(match.vendor, "Nordic AB")
        self.assertEqual(match.method, "visual_logo")

    def test_scale_and_position_changes_are_accepted(self):
        smaller = self.root / "smaller.pdf"
        write_invoice(smaller, self.nordic_png, (48, 70, 178, 113))
        match = match_pdf_logo(smaller, [0], self.profiles, self.root)
        self.assertIsNotNone(match)
        self.assertEqual(match.vendor, "Nordic AB")

    def test_different_logo_does_not_match(self):
        match = match_pdf_logo(
            self.invoice,
            [0],
            [{"vendor": "Other AB", "logo_file": self.other.name}],
            self.root,
        )
        self.assertIsNone(match)

    def test_same_reference_on_two_vendors_is_ambiguous(self):
        profiles = [
            {"vendor": "First AB", "logo_file": self.nordic.name},
            {"vendor": "Second AB", "logo_file": self.nordic.name},
        ]
        match = match_pdf_logo(self.invoice, [0], profiles, self.root)
        self.assertEqual(match.vendor, "")
        self.assertEqual(match.method, "ambiguous_visual_logo")

    def test_broken_reference_and_missing_pdf_are_ignored(self):
        broken = self.root / "broken.svg"
        broken.write_text("<svg>", encoding="utf-8")
        profiles = [{"vendor": "Broken AB", "logo_file": broken.name}]
        self.assertIsNone(match_pdf_logo(self.invoice, [0], profiles, self.root))
        self.assertIsNone(match_pdf_logo(self.root / "missing.pdf", [0], self.profiles, self.root))

    def test_logo_path_cannot_leave_svg_folder(self):
        outside = self.root.parent / "outside-logo.svg"
        outside.write_text(NORDIC_SVG, encoding="utf-8")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        profiles = [{"vendor": "Outside AB", "logo_file": f"../{outside.name}"}]
        self.assertIsNone(match_pdf_logo(self.invoice, [0], profiles, self.root))


class VisualLogoAppIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "visual.sqlite3"
        self.app.SVG_DIR = self.workspace / "svg"
        self.app.SVG_DIR.mkdir(exist_ok=True)
        self.app.init_db()
        self.logo = self.app.SVG_DIR / "nordic.svg"
        self.logo_png = write_svg(self.logo, NORDIC_SVG)
        self.invoice = self.workspace / "invoice.pdf"
        write_invoice(self.invoice, self.logo_png, (355, 42, 535, 99))

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def add_vendor(self, vendor="Nordic AB"):
        with self.app.connect() as db:
            db.execute(
                "INSERT INTO vendor_logos(vendor,logo_file,org_number,bankgiro_number) VALUES(?,?,?,?)",
                (vendor, self.logo.name, "", ""),
            )

    def guess(self, text="Faktura utan leverantörsnamn"):
        return self.app.ReminderApp.guess_supplier(
            SimpleNamespace(), text, path=str(self.invoice), page_indexes=(0,)
        )

    def test_real_app_matches_saved_svg_visually(self):
        self.add_vendor()
        self.assertEqual(self.guess(), "Nordic AB")

    def test_folder_import_uses_visual_match_without_preselected_vendor(self):
        self.add_vendor()
        events = []

        def preview(path, guess, vendor="", page_indexes=None):
            events.append(("preview", vendor))
            return guess

        def add_invoice(**kwargs):
            events.append(("add", kwargs["guess"]["template_vendor"]))

        fake = SimpleNamespace(
            _import_scan_running=False,
            apply_saved_zones=lambda path, vendor, guess, page_indexes=None: guess,
            preview_invoice=preview,
            add_invoice=add_invoice,
            refresh=lambda: None,
            connect=self.app.connect,
        )
        fake.guess_supplier = MethodType(self.app.ReminderApp.guess_supplier, fake)
        section = SimpleNamespace(text="Faktura utan leverantörsnamn", page_indexes=(0,))
        with (
            patch.object(self.app, "read_invoice_candidates", return_value=[(section, {"invoice_no": "WATCH-1"}, "watch-visual")]),
            patch.object(self.app, "show_due_reminder_dialog"),
        ):
            self.app.ReminderApp.scan_import_folder(fake, automatic=True, paths=[self.invoice])
        self.assertEqual(events, [("preview", "Nordic AB"), ("add", "Nordic AB")])

    def test_failed_visual_match_logs_reason_and_manual_review(self):
        other = self.app.SVG_DIR / "other.svg"
        write_svg(other, OTHER_SVG)
        with self.app.connect() as db:
            db.execute(
                "INSERT INTO vendor_logos(vendor,logo_file,org_number,bankgiro_number) VALUES(?,?,?,?)",
                ("Other AB", other.name, "", ""),
            )
        with patch.object(self.app.logger, "warning") as warning:
            self.assertEqual(self.guess(), "")
        messages = [call.args[0] for call in warning.call_args_list]
        self.assertTrue(any("acceptance threshold" in message for message in messages))
        self.assertTrue(any("manual review required" in message for message in messages))

    def test_visual_ambiguity_does_not_fall_back_to_company_name_guess(self):
        self.add_vendor("First AB")
        self.add_vendor("Second AB")
        self.assertEqual(self.guess("Faktura\nSnickeriet AB\nATT BETALA 100 SEK"), "")

    def test_exact_identifier_match_does_not_run_visual_matching(self):
        self.add_vendor()
        with self.app.connect() as db:
            db.execute("UPDATE vendor_logos SET org_number='5561234567'")
        with patch.object(self.app, "match_pdf_logo", wraps=self.app.match_pdf_logo) as visual:
            self.assertEqual(self.guess("Org.nr 556123-4567"), "Nordic AB")
        visual.assert_not_called()


if __name__ == "__main__":
    unittest.main()
