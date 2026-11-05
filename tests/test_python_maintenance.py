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
        self.assertEqual(calls[0][1]["creationflags"], 0)

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


class AddonSchedulerTests(unittest.TestCase):
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
            _quitting=False,
            _python_addon_maintenance_attempted_week="",
            _python_addon_install_running=False,
            update_python_addons=Mock(),
            _run_scheduled_python_addon_maintenance="next-maintenance",
            after=Mock(),
        )

    def run_scheduler(self, fake, moment, marker=""):
        with patch.object(self.app, "datetime") as current_datetime, patch.object(
            self.app, "read_maintenance_week", return_value=marker,
        ):
            current_datetime.now.return_value = moment
            self.app.ReminderApp._run_scheduled_python_addon_maintenance(fake)

    def test_scheduler_waits_for_monday_eight_and_reschedules(self):
        fake = self.fake_app()
        self.run_scheduler(fake, datetime(2026, 11, 2, 7, 59))
        fake.update_python_addons.assert_not_called()
        fake.after.assert_called_once_with(
            maintenance.MAINTENANCE_POLL_INTERVAL_MS, "next-maintenance",
        )

    def test_scheduler_claims_one_catch_up_per_week(self):
        fake = self.fake_app()
        moment = datetime(2026, 11, 3, 9, 0)
        self.run_scheduler(fake, moment, marker="2026-10-26")
        self.run_scheduler(fake, moment, marker="2026-10-26")
        fake.update_python_addons.assert_called_once_with()
        self.assertEqual(fake._python_addon_maintenance_attempted_week, "2026-11-02")

    def test_scheduler_does_not_overlap_startup_recovery(self):
        fake = self.fake_app()
        fake._python_addon_install_running = True
        self.run_scheduler(fake, datetime(2026, 11, 3, 9, 0), marker="2026-10-26")
        fake.update_python_addons.assert_not_called()
        self.assertEqual(fake._python_addon_maintenance_attempted_week, "")

    def test_windows_scheduler_leaves_pre_start_update_to_the_launcher(self):
        fake = self.fake_app()
        with patch.object(self.app.sys, "platform", "win32"):
            self.run_scheduler(fake, datetime(2026, 11, 3, 9, 0), marker="2026-10-26")
            self.assertFalse(self.app.ReminderApp.update_python_addons(fake))
        fake.update_python_addons.assert_not_called()


if __name__ == "__main__":
    unittest.main()
