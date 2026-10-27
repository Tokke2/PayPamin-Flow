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


if __name__ == "__main__":
    unittest.main()
