import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import python_maintenance as maintenance
from test_database import load_headless_app


class PythonMaintenanceTests(unittest.TestCase):
    def test_monday_eight_is_the_only_new_weekly_attempt(self):
        self.assertFalse(maintenance.maintenance_due(datetime(2026, 11, 2, 7, 59), ""))
        self.assertTrue(maintenance.maintenance_due(datetime(2026, 11, 2, 8, 0), ""))
        self.assertFalse(maintenance.maintenance_due(datetime(2026, 11, 3, 9, 0), "2026-11-02"))
        self.assertTrue(maintenance.maintenance_due(datetime(2026, 11, 3, 9, 0), "2026-10-26"))

    def test_next_week_waits_until_monday_eight_again(self):
        self.assertFalse(maintenance.maintenance_due(datetime(2026, 11, 9, 7, 59), "2026-11-02"))
        self.assertTrue(maintenance.maintenance_due(datetime(2026, 11, 9, 8, 0), "2026-11-02"))
        self.assertEqual(maintenance.maintenance_week(datetime(2027, 1, 1, 12)), "2026-12-28")

    def test_week_marker_is_atomic_and_round_trips(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            marker = Path(temp_dir) / "nested" / "python-addons-week.txt"
            self.assertEqual(maintenance.read_maintenance_week(marker), "")
            maintenance.write_maintenance_week(marker, "2026-11-02")
            self.assertEqual(maintenance.read_maintenance_week(marker), "2026-11-02")
            self.assertEqual(list(marker.parent.glob(".python-addons-week.txt.*")), [])

    def test_weekly_upgrade_uses_current_python_without_a_new_environment(self):
        calls = []

        def runner(args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(returncode=0, stdout="updated", stderr="")

        ok, _details = maintenance.install_python_addons(
            r"C:\Python\python.exe", ["PyMuPDF>=1.23", "Pillow>=10.0"], upgrade=True, runner=runner,
        )
        self.assertTrue(ok)
        args = calls[0][0]
        self.assertEqual(args[:4], [r"C:\Python\python.exe", "-m", "pip", "install"])
        self.assertIn("--upgrade", args)
        self.assertIn("only-if-needed", args)
        self.assertNotIn("--user", args)
        self.assertNotIn("venv", " ".join(args).lower())
        self.assertEqual(
            calls[0][1]["creationflags"],
            getattr(maintenance.subprocess, "CREATE_NO_WINDOW", 0),
        )

    def test_addon_requirements_match_requirements_file(self):
        requirements_path = Path(__file__).resolve().parents[1] / "requirements.txt"
        requirements = tuple(
            line.strip() for line in requirements_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        self.assertCountEqual(maintenance.addon_package_specs(), requirements)

    def test_startup_recovery_does_not_upgrade_existing_packages(self):
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        ok, _details = maintenance.install_python_addons(
            "python", ["PyMuPDF>=1.23"], upgrade=False, runner=runner,
        )
        self.assertTrue(ok)
        self.assertNotIn("--upgrade", calls[0])
        self.assertNotIn("--upgrade-strategy", calls[0])

    def test_user_site_retry_preserves_upgrade_flags(self):
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            return SimpleNamespace(returncode=1 if len(calls) == 1 else 0, stdout="", stderr="retry")

        ok, _details = maintenance.install_python_addons(
            "python", ["Pillow>=10.0"], upgrade=True, runner=runner,
        )
        self.assertTrue(ok)
        self.assertEqual(len(calls), 2)
        self.assertIn("--user", calls[1])
        self.assertIn("--upgrade", calls[1])

    def test_empty_package_list_does_not_invoke_pip(self):
        runner = Mock()
        self.assertEqual(maintenance.install_python_addons("python", [], runner=runner), (True, ""))
        runner.assert_not_called()

    def test_missing_package_detection_is_only_for_recovery(self):
        with patch.object(maintenance.importlib.util, "find_spec", side_effect=lambda name: None if name == "fitz" else object()):
            self.assertEqual(maintenance.missing_addon_package_specs(), ("PyMuPDF>=1.23",))


class ImmediateThread:
    def __init__(self, target, daemon):
        self.target = target

    def start(self):
        self.target()


class AddonUpdateOfferTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.app = load_headless_app(Path(self.temporary_directory.name))

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary_directory.cleanup()

        self.addCleanup(cleanup)

    @staticmethod
    def fake_app():
        return SimpleNamespace(
            _python_addon_install_running=False,
            _python_addon_updates_running=False,
            _python_addons_ready=False,
            after=Mock(),
            start_tray=Mock(),
        )

    def test_update_is_declined_without_starting_pip(self):
        fake = self.fake_app()
        with patch.object(self.app.messagebox, "askyesno", return_value=False, create=True), patch.object(
            self.app.threading, "Thread",
        ) as thread:
            self.assertFalse(self.app.ReminderApp.update_python_addons(fake))
        thread.assert_not_called()
        self.assertFalse(fake._python_addon_install_running)

    def test_confirmed_update_uses_existing_interpreter_on_windows(self):
        fake = self.fake_app()
        fake.after.side_effect = lambda _delay, callback: callback()
        with patch.object(self.app.messagebox, "askyesno", return_value=True, create=True), patch.object(
            self.app.messagebox, "showinfo", create=True,
        ), patch.object(self.app.threading, "Thread", ImmediateThread), patch.object(
            self.app, "addon_package_specs", return_value=("Pillow>=10.0",),
        ), patch.object(self.app, "install_python_addons", return_value=(True, "")) as install:
            with patch.object(self.app.sys, "platform", "win32"):
                self.assertTrue(self.app.ReminderApp.update_python_addons(fake))
        install.assert_called_once_with(self.app.sys.executable, ("Pillow>=10.0",), upgrade=True)
        self.assertTrue(fake._python_addons_ready)
        self.assertFalse(fake._python_addon_install_running)
        fake.start_tray.assert_called_once_with()

    def test_running_recovery_is_not_interrupted_by_manual_update(self):
        fake = self.fake_app()
        fake._python_addon_install_running = True
        with patch.object(self.app.messagebox, "showinfo", create=True) as info, patch.object(
            self.app.messagebox, "askyesno", create=True,
        ) as confirm:
            self.assertFalse(self.app.ReminderApp.update_python_addons(fake))
        info.assert_called_once()
        confirm.assert_not_called()


if __name__ == "__main__":
    unittest.main()
