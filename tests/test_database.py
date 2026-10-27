import importlib.util
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_headless_app(workspace):
    """Load the real app module without importing Tkinter or opening a UI."""
    tk = types.ModuleType("tkinter")
    tk.__path__ = []
    tk.Tk = type("Tk", (), {})
    modules = {"tkinter": tk}
    for name in ("font", "ttk", "filedialog", "messagebox", "simpledialog"):
        submodule = types.ModuleType(f"tkinter.{name}")
        setattr(tk, name, submodule)
        modules[f"tkinter.{name}"] = submodule

    script = workspace / "paypamin_flow.py"
    shutil.copyfile(ROOT / "paypamin_flow.py", script)
    spec = importlib.util.spec_from_file_location("paypamin_flow_database_test", script)
    app = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules), patch.object(Path, "home", return_value=workspace):
        spec.loader.exec_module(app)
    return app


class DatabaseTests(unittest.TestCase):
    def test_existing_invoices_gain_sek_currency_without_changing_amounts(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            app = load_headless_app(workspace)
            database_path = workspace / "legacy.sqlite3"
            app.DB_PATH = database_path
            try:
                with app.connect() as db:
                    db.execute(
                        """CREATE TABLE invoices (
                        id INTEGER PRIMARY KEY, customer TEXT NOT NULL, invoice_no TEXT NOT NULL,
                        due_date TEXT NOT NULL, invoice_date TEXT DEFAULT '', template_vendor TEXT DEFAULT '',
                        reviewed INTEGER NOT NULL DEFAULT 1, amount REAL NOT NULL DEFAULT 0,
                        paid REAL NOT NULL DEFAULT 0, email TEXT DEFAULT '', source TEXT DEFAULT '',
                        ignored INTEGER NOT NULL DEFAULT 0, note TEXT DEFAULT '', p1_date TEXT DEFAULT '',
                        p2_date TEXT DEFAULT '', sent_count INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL
                        )"""
                    )
                    db.execute(
                        "INSERT INTO invoices(customer,invoice_no,due_date,amount,paid,created) VALUES(?,?,?,?,?,?)",
                        ("Befintlig kund", "6258", "2026-10-03", 6563.0, 1000.0, "2026-09-03"),
                    )

                app.init_db()
                app.init_db()  # Migration must also be safe on subsequent starts.
                self.assertEqual(app.setting('update_auto'), '1')
                self.assertEqual(app.setting('auto_import'), '1')
                self.assertEqual(app.setting('cache_auto'), '1')
                self.assertEqual(app.setting('cache_last_cleanup'), '')

                with app.connect() as db:
                    columns = {row[1] for row in db.execute("PRAGMA table_info(invoices)")}
                    existing = db.execute(
                        "SELECT amount,paid,currency,logo_file,p1_snapshot FROM invoices WHERE invoice_no='6258'"
                    ).fetchone()
                    self.assertIn("currency", columns)
                    self.assertIn("source_hash", columns)
                    self.assertIn("logo_file", columns)
                    self.assertIn("p1_snapshot", columns)
                    self.assertEqual(tuple(existing), (6563.0, 1000.0, "SEK", None, ""))

                    db.execute(
                        "INSERT INTO invoices(customer,invoice_no,due_date,created) VALUES(?,?,?,?)",
                        ("Ny kund", "7001", "2026-11-01", "2026-10-23"),
                    )
                    new_currency = db.execute(
                        "SELECT currency FROM invoices WHERE invoice_no='7001'"
                    ).fetchone()[0]
                    self.assertEqual(new_currency, "SEK")
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()


if __name__ == "__main__":
    unittest.main()
