import ast
import unittest
from pathlib import Path
from unittest.mock import patch

import donations
import i18n


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


class LockedSwishTests(unittest.TestCase):
    def test_only_swish_exists(self):
        """PayPal and Ko-fi are gone for good."""
        for name in ("PAYPAL_URL", "KOFI_URL", "CHANNELS", "Channel", "paypal_link", "kofi_link", "links"):
            self.assertFalse(hasattr(donations, name), name)
        source = (ROOT / "donations.py").read_text(encoding="utf-8").lower()
        self.assertNotIn("paypal", source)
        self.assertNotIn("ko-fi", source)
        self.assertNotIn("kofi", source)

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

    def test_the_module_offers_no_setter_and_no_link(self):
        self.assertEqual([name for name in dir(donations) if name.lower().startswith("set")], [])
        source = (ROOT / "donations.py").read_text(encoding="utf-8")
        self.assertNotIn("http", source)
        self.assertNotIn("webbrowser", source)


class DonationPanelSourceTests(unittest.TestCase):
    """The support UI is inline in the main window: no page, no second window."""

    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "paypamin_flow.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename="paypamin_flow.py")

    def method(self, name):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        self.fail(f"{name} not found")

    def test_the_help_menu_toggles_the_panel(self):
        self.assertIn(
            "help_menu.add_command(label=_('Stöd appen med Swish'),command=self.toggle_donations)",
            self.source,
        )
        self.assertNotIn("self.show_donations", self.source)

    def test_the_panel_never_opens_a_second_window(self):
        for name in ("_build_donation_panel", "toggle_donations", "_choose_donation_amount"):
            node = self.method(name)
            calls = {
                getattr(inner.func, "attr", "") or getattr(inner.func, "id", "")
                for inner in ast.walk(node)
                if isinstance(inner, ast.Call)
            }
            self.assertNotIn("Toplevel", calls, name)
            self.assertNotIn("_new_toplevel", calls, name)

    def test_the_panel_has_no_entry_field_and_no_setting(self):
        node = self.method("_build_donation_panel")
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

    def test_the_panel_reads_amounts_from_the_locked_module(self):
        node = self.method("_build_donation_panel")
        calls = {
            getattr(inner.func, "attr", "")
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call)
        }
        self.assertIn("amounts", calls)
        self.assertIn("default_amount", calls)

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

    def test_nothing_in_the_app_reaches_the_network_for_a_donation(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in {"open", "urlopen"}:
                arguments = [argument.value for argument in node.args if isinstance(argument, ast.Constant)]
                self.assertFalse(
                    [value for value in arguments if isinstance(value, str) and "donat" in value.lower()],
                )

    def test_no_donation_value_is_stored_in_the_database(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "set_setting":
                values = [argument.value for argument in node.args if isinstance(argument, ast.Constant)]
                self.assertFalse([value for value in values if isinstance(value, str) and "donat" in value.lower()])

    def test_the_panel_strings_are_translated(self):
        missing = []
        for name in ("_build_donation_panel", "_choose_donation_amount", "_show_donation_fallback"):
            for inner in ast.walk(self.method(name)):
                if isinstance(inner, ast.Call) and getattr(inner.func, "id", "") == "_":
                    if inner.args and isinstance(inner.args[0], ast.Constant):
                        key = inner.args[0].value
                        if key not in i18n.translation_keys():
                            missing.append(key)
        self.assertEqual(missing, [])


class DonationPackagingTests(unittest.TestCase):
    def test_the_locked_modules_are_part_of_the_release(self):
        import app_info

        for name in ("donations.py", "qr_code.py"):
            self.assertIn(name, app_info.PYTHON_PACKAGE_REQUIRED_FILES)
            self.assertTrue(app_info.is_python_package_file(name), name)


if __name__ == "__main__":
    unittest.main()
