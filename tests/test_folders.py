import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_database import load_headless_app


class FolderActionTests(unittest.TestCase):
    def test_open_export_folder_creates_folder_and_uses_system_file_manager(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            app = load_headless_app(workspace)
            export_dir = workspace / "new-export"
            app.EXPORT_DIR = export_dir
            try:
                with patch.object(app, "open_path") as open_path:
                    app.ReminderApp.open_export_folder(SimpleNamespace())
                self.assertTrue(export_dir.is_dir())
                open_path.assert_called_once_with(export_dir)
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()

    def test_open_print_folder_opens_the_folder_shipped_in_the_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            app = load_headless_app(workspace)
            print_dir = workspace / "assets" / "print"
            print_dir.mkdir(parents=True)
            app.PRINT_DIR = print_dir
            try:
                with patch.object(app, "open_path") as open_path:
                    app.ReminderApp.open_print_folder(SimpleNamespace())
                open_path.assert_called_once_with(print_dir)
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()

    def test_open_print_folder_explains_a_missing_installation(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            app = load_headless_app(workspace)
            app.PRINT_DIR = workspace / "missing-print-folder"
            try:
                with patch.object(app, "open_path") as open_path, \
                        patch.object(app.messagebox, "showwarning", create=True) as warning:
                    app.ReminderApp.open_print_folder(SimpleNamespace())
                open_path.assert_not_called()
                self.assertEqual(warning.call_count, 1)
                self.assertIn("assets", warning.call_args.args[1])
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()


if __name__ == "__main__":
    unittest.main()
