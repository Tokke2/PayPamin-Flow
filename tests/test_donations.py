import ast
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import donations
import i18n
import qr_code
from test_database import load_headless_app


ROOT = Path(__file__).resolve().parents[1]


class LockedAmountTests(unittest.TestCase):
    def test_the_amounts_and_the_default_are_fixed(self):
        self.assertEqual(donations.amounts(), (25, 50, 100, 200))
        self.assertEqual(donations.default_amount(), 50)
        self.assertIsInstance(donations.AMOUNTS, tuple)
        self.assertIn(donations.default_amount(), donations.AMOUNTS)

    def test_only_the_fixed_amounts_are_accepted(self):
        for amount in donations.AMOUNTS:
            self.assertEqual(donations.normalize_amount(amount), amount)
            self.assertTrue(donations.is_fixed_amount(amount))
        for invalid in (0, 1, 37, 149, 150, 1000, -50, 50.5, "50,5", "mycket", None, True):
            with self.subTest(invalid=invalid):
                self.assertFalse(donations.is_fixed_amount(invalid))
                with self.assertRaises(ValueError):
                    donations.normalize_amount(invalid)

    def test_a_free_amount_never_becomes_a_payment_code(self):
        for amount in donations.AMOUNTS:
            self.assertIn(f";{amount};;", donations.swish_payload(amount))
        with self.assertRaises(ValueError):
            donations.swish_payload(37)
        with self.assertRaises(ValueError):
            donations.summary(37)

    def test_a_decimal_is_never_rounded_into_a_fixed_amount(self):
        with self.assertRaises(ValueError):
            donations.normalize_amount(50.9)
        with self.assertRaises(ValueError):
            donations.normalize_amount("50.9")

    def test_the_summary_names_the_locked_number(self):
        text = donations.summary()
        self.assertIn("50 SEK", text)
        self.assertIn("0721-817 177", text)


class LockedChannelTests(unittest.TestCase):
    def test_all_three_channels_are_locked_constants(self):
        self.assertIsInstance(donations.CHANNELS, tuple)
        self.assertEqual([item.key for item in donations.CHANNELS], ["paypal", "kofi"])
        for item in donations.CHANNELS:
            with self.assertRaises(FrozenInstanceError):
                item.url = "https://example.com"
        self.assertEqual(donations.channel("PayPal").url, donations.PAYPAL_URL)
        with self.assertRaises(KeyError):
            donations.channel("swish-swish")

    def test_only_the_authors_pages_can_be_opened(self):
        self.assertTrue(donations.is_locked_address(donations.PAYPAL_URL))
        self.assertTrue(donations.is_locked_address(donations.paypal_link(100)))
        self.assertTrue(donations.is_locked_address(donations.kofi_link()))
        for foreign in (
            "https://example.com",
            "https://paypal.me/SomeoneElse",
            "https://paypal.me/Rickard3dPrint.evil.example",
            "https://paypal.me/Rickard3dPrint/abcSEK",
            "javascript:alert(1)",
            "",
            None,
        ):
            with self.subTest(foreign=foreign):
                self.assertFalse(donations.is_locked_address(foreign))

    def test_the_paypal_amount_link_is_still_the_author_page(self):
        for amount in donations.AMOUNTS:
            link = donations.paypal_link(amount)
            self.assertEqual(link, f"https://paypal.me/Rickard3dPrint/{amount}SEK")
            self.assertTrue(donations.is_locked_address(link))
        with self.assertRaises(ValueError):
            donations.paypal_link(37)

    def test_the_number_is_locked_and_formatted(self):
        self.assertEqual(donations.swish_number(), "0721817177")
        self.assertEqual(donations.formatted_number(), "0721-817 177")
        with patch.object(donations, "SWISH_NUMBER", "0721 817 177"):
            self.assertEqual(donations.swish_number(), "0721817177")
            self.assertEqual(donations.formatted_number(), "0721-817 177")

    def test_the_payload_follows_the_standard_swish_format(self):
        self.assertEqual(donations.SWISH_EDIT_MASK, 6)
        self.assertEqual(donations.swish_payload(), "C0721817177;50;;6")
        for amount in donations.AMOUNTS:
            payload = donations.swish_payload(amount)
            self.assertEqual(payload, f"C0721817177;{amount};;6")
            self.assertEqual(payload.count(";"), 3)

    def test_only_the_fixed_amounts_reach_the_payload(self):
        with self.assertRaises(ValueError):
            donations.swish_payload(37)
        with self.assertRaises(ValueError):
            donations.swish_payload("150 kr")

    def test_the_module_offers_no_setter(self):
        self.assertEqual([name for name in dir(donations) if name.lower().startswith("set")], [])
        source = (ROOT / "donations.py").read_text(encoding="utf-8")
        self.assertNotIn("webbrowser", source)
        self.assertNotIn("open(", source)


class DonationDialogSourceTests(unittest.TestCase):
    """Donations live in their own dialogue under Help, with three channels."""

    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "paypamin_flow.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename="paypamin_flow.py")

    def method(self, name):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        self.fail(f"{name} not found")

    def test_the_help_menu_opens_the_dialogue(self):
        self.assertIn(
            "help_menu.add_command(label=_('Stöd PayPamin Flow'),command=self.show_donations)",
            self.source,
        )
        self.assertNotIn("self.toggle_donations", self.source)

    def test_the_dialogue_is_its_own_window(self):
        node = self.method("show_donations")
        calls = {
            getattr(inner.func, "attr", "") or getattr(inner.func, "id", "")
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call)
        }
        self.assertIn("_new_toplevel", calls)
        # Opening it twice must raise the window that is already open.
        self.assertIn("deiconify", calls)
        self.assertIn("lift", calls)

    def test_the_dialogue_offers_swish_paypal_and_kofi(self):
        node = self.method("show_donations")
        calls = {
            getattr(inner.func, "attr", "")
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call)
        }
        for expected in ("paypal_link", "kofi_link", "amounts", "default_amount", "_choose_donation_amount"):
            self.assertIn(expected, calls)
        # The Swish code itself is drawn through the locked payload.
        self.assertIn("swish_payload", {
            getattr(inner.func, "attr", "")
            for inner in ast.walk(self.method("_draw_donation_qr"))
            if isinstance(inner, ast.Call)
        })
        texts = [
            inner.value for inner in ast.walk(node)
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str)
        ]
        self.assertIn("Öppna PayPal", texts)
        self.assertIn("Öppna Ko-fi", texts)
        self.assertIn("Swish", texts)

    def test_the_dialogue_has_no_entry_field_and_no_setting(self):
        node = self.method("show_donations")
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call):
                name = getattr(inner.func, "id", None) or getattr(inner.func, "attr", None)
                self.assertNotIn(name, {"Entry", "Spinbox", "set_setting", "setting"}, name)
                if name in {"Button", "Combobox"}:
                    self.assertNotIn("textvariable", {keyword.arg for keyword in inner.keywords})
        for inner in ast.walk(node):
            if isinstance(inner, ast.Assign):
                for target in inner.targets:
                    owner = getattr(getattr(target, "value", None), "id", None)
                    self.assertNotEqual(owner, "donations")

    def test_the_code_is_drawn_locally_and_never_fetched(self):
        node = self.method("_draw_donation_qr")
        calls = {
            getattr(inner.func, "attr", "") or getattr(inner.func, "id", "")
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call)
        }
        self.assertIn("encode", calls)
        self.assertIn("swish_payload", calls)
        self.assertNotIn("webbrowser", calls)
        self.assertNotIn("urlopen", calls)

    def test_every_link_is_checked_before_the_browser_opens(self):
        node = self.method("_open_donation_link")
        names = {
            getattr(inner.func, "attr", "") or getattr(inner.func, "id", "")
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call)
        }
        self.assertIn("is_locked_address", names)
        self.assertIn("open", names)

    def test_no_donation_value_is_stored_in_the_database(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "set_setting":
                values = [argument.value for argument in node.args if isinstance(argument, ast.Constant)]
                self.assertFalse([value for value in values if isinstance(value, str) and "donat" in value.lower()])

    def test_the_dialogue_strings_are_translated(self):
        missing = []
        for name in ("show_donations", "_copy_swish_number"):
            for inner in ast.walk(self.method(name)):
                if isinstance(inner, ast.Call) and getattr(inner.func, "id", "") == "_":
                    if inner.args and isinstance(inner.args[0], ast.Constant):
                        key = inner.args[0].value
                        if key not in i18n.translation_keys():
                            missing.append(key)
        self.assertEqual(missing, [])


class FakeCanvas:
    """Record what the dialogue would paint on its Swish canvas."""

    def __init__(self):
        self.calls = []
        self.options = {}

    def configure(self, **options):
        self.options.update(options)

    def delete(self, *args):
        self.calls.append(("delete", args))

    def create_rectangle(self, *args, **options):
        self.calls.append(("rect", args, options["fill"]))


class FakeButton:
    def __init__(self):
        self.style = None

    def configure(self, **options):
        if "style" in options:
            self.style = options["style"]


class FakeLabel:
    def __init__(self):
        self.text = ""

    def configure(self, **options):
        if "text" in options:
            self.text = options["text"]


class DonationDrawingTests(unittest.TestCase):
    """The drawing and amount logic, without a display."""

    def setUp(self):
        self.app = load_headless_app(Path(tempfile.mkdtemp()))

    def owner(self, amount=None):
        owner = SimpleNamespace(
            donation_canvas=FakeCanvas(),
            donation_amount=donations.default_amount() if amount is None else amount,
            donation_buttons={value: FakeButton() for value in donations.AMOUNTS},
            donation_amount_label=FakeLabel(),
        )
        owner._px = lambda value: value
        owner._donation_qr_size = lambda: (len(qr_code.encode(donations.swish_payload(donations.default_amount()))) + 8, 1)
        # Binding the real method keeps the drawing path intact.
        owner._draw_donation_qr = lambda amount=None: self.app.ReminderApp._draw_donation_qr(owner, amount)
        return owner

    def test_the_canvas_is_painted_white_before_the_modules(self):
        owner = self.owner()
        self.assertTrue(self.app.ReminderApp._draw_donation_qr(owner))
        rectangles = [call for call in owner.donation_canvas.calls if call[0] == "rect"]
        self.assertEqual(rectangles[0][2], "#FFFFFF")

    def test_only_dark_modules_are_drawn(self):
        owner = self.owner()
        self.app.ReminderApp._draw_donation_qr(owner)
        rects = [call for call in owner.donation_canvas.calls if call[0] == "rect"]
        expected = sum(1 for row in qr_code.encode(donations.swish_payload(50)) for value in row if value)
        self.assertEqual(len(rects), expected + 1)  # plus the white background
        self.assertTrue(all(call[2] == "#000000" for call in rects[1:]))

    def test_the_code_follows_the_selected_amount(self):
        owner = self.owner()
        self.app.ReminderApp._choose_donation_amount(owner, 200)
        self.assertEqual(owner.donation_amount, 200)
        self.assertEqual(owner.donation_buttons[200].style, "Accent.TButton")
        self.assertEqual(owner.donation_buttons[50].style, "TButton")
        self.assertIn("200", owner.donation_amount_label.text)
        self.assertTrue(owner.donation_canvas.calls)

    def test_a_free_amount_is_ignored_instead_of_drawn(self):
        owner = self.owner()
        self.app.ReminderApp._choose_donation_amount(owner, 137)
        self.assertEqual(owner.donation_amount, donations.default_amount())
        self.assertEqual(owner.donation_canvas.calls, [])


class DonationPackagingTests(unittest.TestCase):
    def test_the_locked_modules_are_part_of_the_release(self):
        import app_info

        for name in ("donations.py", "qr_code.py"):
            self.assertIn(name, app_info.PYTHON_PACKAGE_REQUIRED_FILES)
            self.assertTrue(app_info.is_python_package_file(name), name)


if __name__ == "__main__":
    unittest.main()
