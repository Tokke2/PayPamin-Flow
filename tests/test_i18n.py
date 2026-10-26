import ast
import string
import unittest
from datetime import date
from pathlib import Path

import i18n
from i18n import _, format_long_date, format_money, get_language, language_code, set_language


ROOT = Path(__file__).resolve().parents[1]
TRANSLATED_MODULES = [
    ROOT / "paypamin_flow.py",
    ROOT / "app_backup.py",
    ROOT / "autostart.py",
    ROOT / "invoice_parser.py",
    ROOT / "update_checker.py",
    ROOT / "update_installer.py",
]


def format_fields(text):
    return {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(text)
        if field_name
    }


class TranslationTests(unittest.TestCase):
    def tearDown(self):
        set_language("sv")

    def test_switches_between_swedish_and_english(self):
        self.assertEqual(get_language(), "sv")
        self.assertEqual(_("Inställningar"), "Inställningar")
        set_language("en")
        self.assertEqual(get_language(), "en")
        self.assertEqual(_("Inställningar"), "Settings")
        self.assertEqual(_("Starta {app_name} automatiskt när jag loggar in", app_name="PayPamin Flow"), "Start PayPamin Flow automatically when I log in")

    def test_language_names_and_unknown_fallback(self):
        self.assertEqual(language_code("Svenska"), "sv")
        self.assertEqual(language_code("English"), "en")
        self.assertEqual(language_code("unknown"), "sv")
        set_language("unsupported")
        self.assertEqual(get_language(), "sv")

    def test_money_formats_follow_language(self):
        self.assertEqual(format_money(6563.0), "6 563,00 kr")
        set_language("en")
        self.assertEqual(format_money(6563.0), "SEK 6,563.00")

    def test_long_dates_do_not_depend_on_os_locale(self):
        day = date(2026, 10, 23)
        self.assertEqual(format_long_date(day), "23 oktober 2026")
        set_language("en")
        self.assertEqual(format_long_date(day), "23 October 2026")

    def test_every_literal_translation_call_has_an_english_entry(self):
        missing = []
        for path in TRANSLATED_MODULES:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "_":
                    continue
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    key = node.args[0].value
                    if key not in i18n.translation_keys():
                        missing.append(f"{path.name}:{node.lineno}: {key}")
        self.assertEqual(missing, [])

    def test_translation_calls_supply_all_template_variables(self):
        problems = []
        for path in TRANSLATED_MODULES:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "_":
                    continue
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    expected = format_fields(node.args[0].value)
                    supplied = {keyword.arg for keyword in node.keywords}
                    if expected != supplied:
                        problems.append(f"{path.name}:{node.lineno}: expected {expected}, got {supplied}")
        self.assertEqual(problems, [])

    def test_swedish_and_english_templates_have_matching_variables(self):
        set_language("en")
        mismatches = []
        for key in i18n.translation_keys():
            translated = _(key)
            if format_fields(key) != format_fields(translated):
                mismatches.append(key)
        self.assertEqual(mismatches, [])

    def test_all_english_translations_are_nonempty(self):
        set_language("en")
        self.assertTrue(i18n.translation_keys())
        self.assertEqual([key for key in i18n.translation_keys() if not _(key).strip()], [])


if __name__ == "__main__":
    unittest.main()
