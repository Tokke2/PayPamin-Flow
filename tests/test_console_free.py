import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import console_free
from test_database import load_headless_app


class ConsoleFreeSubprocessTests(unittest.TestCase):
    def tearDown(self):
        console_free._installed = False

    def test_windows_children_preserve_flags_and_add_no_window(self):
        calls = []
        original_popen = console_free.subprocess.Popen
        original_flag = getattr(console_free.subprocess, "CREATE_NO_WINDOW", None)

        def fake_popen(*args, **kwargs):
            calls.append((args, kwargs))
            return object()

        try:
            console_free.subprocess.Popen = fake_popen
            console_free.subprocess.CREATE_NO_WINDOW = 0x08000000
            console_free._installed = False
            with patch.object(console_free.sys, "platform", "win32"):
                console_free.configure_console_free_subprocesses()
                wrapped_popen = console_free.subprocess.Popen
                console_free.configure_console_free_subprocesses()
                self.assertIs(console_free.subprocess.Popen, wrapped_popen)
                console_free.subprocess.Popen("ocr-tool", creationflags=0x08)
                console_free.subprocess.Popen("other-tool")
        finally:
            console_free.subprocess.Popen = original_popen
            if original_flag is None:
                del console_free.subprocess.CREATE_NO_WINDOW
            else:
                console_free.subprocess.CREATE_NO_WINDOW = original_flag
        self.assertEqual(calls[0][1]["creationflags"], 0x08000008)
        self.assertEqual(calls[1][1]["creationflags"], 0x08000000)

    def test_non_windows_does_not_patch_popen(self):
        with patch.object(console_free.sys, "platform", "linux"), patch.object(
            console_free.subprocess, "Popen"
        ) as popen:
            console_free.configure_console_free_subprocesses()
            self.assertIs(console_free.subprocess.Popen, popen)
        self.assertFalse(console_free._installed)


class ApplicationStartupTests(unittest.TestCase):
    def test_main_configures_console_free_children_before_app_start(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = load_headless_app(Path(temporary_directory))
            events = []
            fake_window = SimpleNamespace(mainloop=lambda: events.append("mainloop"))
            try:
                with patch.object(
                    app, "configure_console_free_subprocesses", side_effect=lambda: events.append("console-free")
                ), patch.object(
                    app, "configure_windows_app_identity", side_effect=lambda: events.append("windows-identity")
                ), patch.object(app, "init_db", side_effect=lambda: events.append("database")), patch.object(
                    app, "ReminderApp", return_value=fake_window
                ):
                    app.main()
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()
            self.assertEqual(events, ["console-free", "windows-identity", "database", "mainloop"])

    def test_unexpected_startup_errors_are_logged_and_reraised_for_the_gui_launcher(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = load_headless_app(Path(temporary_directory))
            try:
                with patch.object(app, "configure_console_free_subprocesses"), patch.object(
                    app, "configure_windows_app_identity"
                ), patch.object(app, "init_db", side_effect=RuntimeError("synthetic startup failure")):
                    with self.assertRaisesRegex(RuntimeError, "synthetic startup failure"):
                        app.main()
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()


if __name__ == "__main__":
    unittest.main()
