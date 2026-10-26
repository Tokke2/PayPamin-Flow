import queue
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_database import load_headless_app
from update_checker import UPDATE_CHECK_INTERVAL_MS, ReleaseInfo


RELEASE = ReleaseInfo("0.7.0", "v0.7.0", "https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.7.0")


class UpdateUiTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.app = load_headless_app(Path(self.temporary_directory.name))

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary_directory.cleanup()

        self.addCleanup(cleanup)

    def fake_app(self):
        return SimpleNamespace(
            _update_check_running=True,
            _set_update_check_busy=lambda busy: None,
        )

    def test_automatic_new_release_starts_silent_installation(self):
        fake = self.fake_app()
        calls = []
        fake.start_update_installation = lambda release, manual: calls.append((release.version, manual))
        fake.show_update_available = lambda release: self.fail("Automatic check must not open a dialog")
        results = queue.Queue()
        results.put(("ok", False, RELEASE))
        with patch.object(self.app, "setting", return_value="1"):
            self.app.ReminderApp._poll_update_check(fake, results)
        self.assertEqual(calls, [("0.7.0", False)])

    def test_manual_new_release_shows_choices_instead_of_auto_installing(self):
        fake = self.fake_app()
        calls = []
        fake.show_update_available = lambda release: calls.append(release.version)
        fake.start_update_installation = lambda release, manual: self.fail("Manual check should wait for the install button")
        results = queue.Queue()
        results.put(("ok", True, RELEASE))
        self.app.ReminderApp._poll_update_check(fake, results)
        self.assertEqual(calls, ["0.7.0"])

    def test_scheduler_respects_twice_daily_interval_and_setting(self):
        fake = SimpleNamespace()
        fake._run_scheduled_update_check = "next-scheduled-check"
        scheduled = []
        checks = []
        fake.after = lambda delay, callback: scheduled.append((delay, callback))
        fake.check_for_updates = lambda manual: checks.append(manual)
        with patch.object(self.app, "setting", return_value="1"):
            self.app.ReminderApp._run_scheduled_update_check(fake)
        self.assertEqual(checks, [False])
        self.assertEqual(scheduled, [(UPDATE_CHECK_INTERVAL_MS, "next-scheduled-check")])

        scheduled.clear()
        checks.clear()
        with patch.object(self.app, "setting", return_value="0"):
            self.app.ReminderApp._run_scheduled_update_check(fake)
        self.assertEqual(checks, [])
        self.assertEqual(scheduled, [(UPDATE_CHECK_INTERVAL_MS, "next-scheduled-check")])


if __name__ == "__main__":
    unittest.main()
