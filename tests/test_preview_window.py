import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from test_database import load_headless_app


class PreviewWindowSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = load_headless_app(Path(self.temporary.name))

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def test_row_menu_is_unposted_and_releases_its_grab(self):
        events = []
        menu = SimpleNamespace(
            unpost=lambda: events.append("unpost"),
            grab_release=lambda: events.append("release"),
        )
        fake = SimpleNamespace(row_menu=menu)

        self.app.ReminderApp.dismiss_row_context_menu(fake)

        self.assertEqual(events, ["unpost", "release"])

    def test_preview_cleanup_releases_grab_closes_pdf_and_destroys_window(self):
        events = []
        window = SimpleNamespace(
            grab_release=lambda: events.append("release"),
            winfo_exists=lambda: True,
            destroy=lambda: events.append("destroy"),
        )
        document = SimpleNamespace(close=lambda: events.append("close"))

        self.app.ReminderApp.close_invoice_preview(object(), window, document)

        self.assertEqual(events, ["release", "close", "destroy"])

    def test_preview_window_is_destroyed_even_if_pdf_close_fails(self):
        events = []

        def fail_close():
            events.append("close")
            raise RuntimeError("synthetic PDF close failure")

        window = SimpleNamespace(
            grab_release=lambda: events.append("release"),
            winfo_exists=lambda: True,
            destroy=lambda: events.append("destroy"),
        )
        document = SimpleNamespace(close=fail_close)

        with self.assertRaisesRegex(RuntimeError, "synthetic PDF close failure"):
            self.app.ReminderApp.close_invoice_preview(object(), window, document)
        self.assertEqual(events, ["release", "close", "destroy"])


if __name__ == "__main__":
    unittest.main()
