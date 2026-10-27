import ast
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from test_database import load_headless_app


ROOT = Path(__file__).resolve().parents[1]


class TranslationScopeTests(unittest.TestCase):
    def test_selected_invoice_detail_does_not_shadow_translation_function(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            app = load_headless_app(workspace)
            app.DB_PATH = workspace / "scope.sqlite3"
            app.init_db()
            values = {
                "customer": "Scope Testkund AB",
                "invoice_no": "SCOPE-1",
                "invoice_date": "2026-01-01",
                "due_date": "2000-01-01",
                "template_vendor": "",
                "amount": 100.0,
                "currency": "SEK",
                "paid": 0,
                "email": "",
                "source": "scope-test",
                "source_hash": "scope-source",
                "note": "",
                "reviewed": 1,
                "logo_file": None,
            }
            self.assertIsNone(app.save_invoice_record(values))
            with app.connect() as db:
                row = db.execute("SELECT * FROM invoices WHERE invoice_no='SCOPE-1'").fetchone()
            messages = []
            fake = SimpleNamespace(
                tree=SimpleNamespace(selection=lambda: [str(row["id"])]),
                detail=SimpleNamespace(configure=lambda **kwargs: messages.append(kwargs)),
                invoice_logo=lambda record: ("", "(Ingen logotyp)"),
            )
            try:
                app.ReminderApp.show_detail(fake)
                self.assertEqual(len(messages), 1)
                self.assertIn("Scope Testkund AB", messages[0]["text"])
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()

    def test_translation_function_is_not_used_as_a_local_throwaway(self):
        for filename in ("paypamin_flow.py", "reminder_journal.py"):
            tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"), filename=filename)
            for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
                stores = [
                    node.lineno for node in ast.walk(function)
                    if isinstance(node, ast.Name) and node.id == "_" and isinstance(node.ctx, ast.Store)
                ]
                calls = [
                    node.lineno for node in ast.walk(function)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_"
                ]
                self.assertFalse(
                    stores and calls,
                    f"{filename}:{function.name} shadows the translation function at lines {stores}",
                )


if __name__ == "__main__":
    unittest.main()
