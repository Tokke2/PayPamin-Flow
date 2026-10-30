import queue
import tempfile
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

from app_info import PYTHON_RELEASE_ASSET
from test_database import load_headless_app
from update_checker import UPDATE_CHECK_INTERVAL_MS, ReleaseAsset, ReleaseInfo


PACKAGE_URL = f"https://github.com/Tokke2/PayPamin-Flow/releases/download/v0.7.0/{PYTHON_RELEASE_ASSET}"
RELEASE_ASSETS = (
    ReleaseAsset(PYTHON_RELEASE_ASSET, PACKAGE_URL),
    ReleaseAsset(PYTHON_RELEASE_ASSET + ".sha256", PACKAGE_URL + ".sha256"),
)
RELEASE = ReleaseInfo("0.7.0", "v0.7.0", "https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.7.0", assets=RELEASE_ASSETS)


class ImmediateThread:
    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


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
        fake = SimpleNamespace(
            _update_check_running=True,
            _update_install_running=False,
            _available_update=None,
            update_button=None,
            _set_update_check_busy=lambda busy: None,
        )
        fake._set_update_available = MethodType(self.app.ReminderApp._set_update_available, fake)
        return fake

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

    def test_automatic_incomplete_release_waits_without_installing(self):
        fake = self.fake_app()
        calls = []
        release = ReleaseInfo("0.7.0", "v0.7.0", RELEASE.url)
        fake.start_update_installation = lambda release, manual: calls.append((release.version, manual))
        fake.show_update_available = lambda release: self.fail("Automatic check must not open a dialog")
        results = queue.Queue()
        results.put(("ok", False, release))
        with patch.object(self.app, "setting", return_value="1"):
            self.app.ReminderApp._poll_update_check(fake, results)
        self.assertEqual(calls, [])

    def test_manual_new_release_shows_choices_instead_of_auto_installing(self):
        fake = self.fake_app()
        calls = []
        fake.show_update_available = lambda release: calls.append(release.version)
        fake.start_update_installation = lambda release, manual: self.fail("Manual check should wait for the install button")
        results = queue.Queue()
        results.put(("ok", True, RELEASE))
        self.app.ReminderApp._poll_update_check(fake, results)
        self.assertEqual(calls, ["0.7.0"])

    def test_update_button_opens_cached_release_without_rechecking(self):
        calls = []
        fake = SimpleNamespace(
            _update_check_running=False,
            _update_install_running=False,
            _available_update=RELEASE,
            show_update_available=calls.append,
        )
        with patch.object(self.app.threading, "Thread", side_effect=AssertionError("No network worker expected")):
            self.app.ReminderApp.check_for_updates(fake, manual=True)
        self.assertEqual(calls, [RELEASE])

    def test_available_release_changes_idle_button_text(self):
        self.app.set_language("sv")
        button = Mock()
        fake = SimpleNamespace(
            _available_update=None,
            _update_check_running=False,
            _update_install_running=False,
            update_button=button,
        )
        fake._update_button_idle_text = MethodType(self.app.ReminderApp._update_button_idle_text, fake)
        self.app.ReminderApp._set_update_available(fake, RELEASE)
        button.configure.assert_called_once_with(text="Uppdatering tillgänglig", state="normal")
        self.app.ReminderApp._set_update_available(fake, None)
        self.assertEqual(button.configure.call_args.kwargs["text"], "Uppdatera appen")

    def test_force_check_bypasses_cached_release(self):
        scheduled = []
        fake = SimpleNamespace(
            _update_check_running=False,
            _update_install_running=False,
            _available_update=RELEASE,
            update_button=None,
            _set_update_check_busy=lambda busy: None,
            after=lambda delay, callback: scheduled.append(callback),
        )
        fake._set_update_available = MethodType(self.app.ReminderApp._set_update_available, fake)
        fake._poll_update_check = MethodType(self.app.ReminderApp._poll_update_check, fake)
        with patch.object(self.app, "fetch_latest_release", return_value=RELEASE), patch.object(
            self.app.threading, "Thread", ImmediateThread
        ):
            self.app.ReminderApp.check_for_updates(fake, manual=True, force=True)
        self.assertIsNone(fake._available_update)
        self.assertTrue(fake._update_check_running)
        self.assertEqual(len(scheduled), 1)

    def test_manual_dialog_disables_install_until_files_are_ready(self):
        self.app.set_language("sv")
        window = Mock()
        fake = SimpleNamespace(_new_toplevel=lambda title: window)
        widgets = []

        def make_widget(*args, **kwargs):
            widget = Mock()
            widget.options = kwargs
            widgets.append(widget)
            return widget

        release = ReleaseInfo("0.7.0", "v0.7.0", RELEASE.url)
        with patch.object(self.app.ttk, "Frame", side_effect=make_widget, create=True), patch.object(
            self.app.ttk, "Label", side_effect=make_widget, create=True
        ), patch.object(self.app.ttk, "Button", side_effect=make_widget, create=True):
            self.app.ReminderApp.show_update_available(fake, release)
        install = next(widget for widget in widgets if widget.options.get("text") == "Installera och starta om")
        install.state.assert_called_once_with(["disabled"])
        labels = [widget.options.get("text", "") for widget in widgets]
        self.assertTrue(any("Releasefilerna är inte klara" in text for text in labels))
        self.assertTrue(any("Typ av uppdatering:" in text for text in labels))

    def test_same_version_release_build_uses_release_comparison(self):
        fake = self.fake_app()
        release = ReleaseInfo("0.6.0", "v0.6.0", "https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.6.0", release_id="200")
        calls = []
        fake.show_update_available = lambda value: calls.append(value.release_id)
        results = queue.Queue()
        results.put(("ok", True, release))
        with patch.object(self.app, "is_update_available", return_value=True) as compare:
            self.app.ReminderApp._poll_update_check(fake, results)
        compare.assert_called_once_with(release, "0.6.0")
        self.assertEqual(calls, ["200"])

    def test_install_cannot_start_until_release_files_are_ready(self):
        fake = SimpleNamespace(_update_install_running=False)
        release = ReleaseInfo("0.7.0", "v0.7.0", RELEASE.url)
        with patch.object(self.app.threading, "Thread", side_effect=AssertionError("No worker may start")):
            self.app.ReminderApp.start_update_installation(fake, release, manual=False)
        self.assertFalse(fake._update_install_running)

    def test_progress_updates_button_and_keeps_polling(self):
        events = []
        scheduled = []
        fake = SimpleNamespace(
            _update_install_running=True,
            _set_update_install_busy=lambda busy, stage=None: events.append((busy, stage)),
            after=lambda delay, callback: scheduled.append(callback),
        )
        fake._poll_update_installation = MethodType(self.app.ReminderApp._poll_update_installation, fake)
        results = queue.Queue()
        results.put(("progress", True, RELEASE, "download"))
        self.app.ReminderApp._poll_update_installation(fake, results)
        self.assertEqual(events, [(True, "download")])
        self.assertEqual(len(scheduled), 1)
        self.assertTrue(fake._update_install_running)

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

    def test_successful_python_install_waits_for_ready_then_closes(self):
        installed = object()
        events = []
        scheduled = []
        fake = SimpleNamespace(
            _update_helper_process=None,
            _update_install_running=True,
            _set_update_install_busy=lambda busy: events.append(("busy", busy)),
            _quitting=False,
            tray=None,
            after=lambda delay, callback: scheduled.append(callback),
            destroy=lambda: events.append("destroyed"),
        )
        fake._update_restart_failed = MethodType(self.app.ReminderApp._update_restart_failed, fake)
        fake._poll_update_installation = MethodType(self.app.ReminderApp._poll_update_installation, fake)
        results = queue.Queue()
        results.put(("restart", False, RELEASE, installed))
        process = SimpleNamespace(pid=123)
        with patch.object(self.app, "restart_updated_app", return_value=process) as restart, patch.object(
            self.app, "wait_for_update_restart", return_value=None
        ) as wait, patch.object(self.app.threading, "Thread", ImmediateThread), patch.object(
            self.app, "cleanup_update"
        ) as cleanup:
            self.app.ReminderApp._poll_update_installation(fake, results)
            self.assertEqual(events, [])
            cleanup.assert_not_called()
            self.assertFalse(fake._quitting)
            scheduled.pop(0)()
        restart.assert_called_once_with(installed)
        wait.assert_called_once_with(installed, process)
        cleanup.assert_called_once_with(installed)
        self.assertEqual(fake._update_helper_process, process)
        self.assertTrue(fake._quitting)
        self.assertEqual(events, ["destroyed"])

    def test_failed_ready_handshake_rolls_back_without_closing_old_app(self):
        installed = object()
        events = []
        scheduled = []
        fake = SimpleNamespace(
            _update_helper_process=None,
            _update_install_running=True,
            _set_update_install_busy=lambda busy: events.append(("busy", busy)),
            _quitting=False,
            tray=None,
            after=lambda delay, callback: scheduled.append(callback),
            destroy=lambda: events.append("destroyed"),
            _show_update_install_error=lambda release, error: self.fail("Automatic failure must stay silent"),
        )
        fake._update_restart_failed = MethodType(self.app.ReminderApp._update_restart_failed, fake)
        fake._poll_update_installation = MethodType(self.app.ReminderApp._poll_update_installation, fake)
        results = queue.Queue()
        results.put(("restart", False, RELEASE, installed))
        process = SimpleNamespace(pid=123)
        with patch.object(self.app, "restart_updated_app", return_value=process), patch.object(
            self.app, "wait_for_update_restart", side_effect=self.app.UpdateInstallError("not ready")
        ), patch.object(self.app.threading, "Thread", ImmediateThread), patch.object(
            self.app, "rollback_update"
        ) as rollback, patch.object(self.app, "cleanup_update") as cleanup:
            self.app.ReminderApp._poll_update_installation(fake, results)
            scheduled.pop(0)()
        rollback.assert_called_once_with(installed)
        cleanup.assert_called_once_with(installed)
        self.assertFalse(fake._quitting)
        self.assertFalse(fake._update_install_running)
        self.assertNotIn("destroyed", events)
        self.assertEqual(events, [("busy", False)])

    def test_failed_restart_rolls_back_python_files(self):
        installed = object()
        events = []
        fake = SimpleNamespace(
            _update_install_running=True,
            _update_helper_process=None,
            _set_update_install_busy=lambda busy: events.append(("busy", busy)),
            _show_update_install_error=lambda release, error: self.fail("Automatic failure must stay silent"),
        )
        fake._update_restart_failed = MethodType(self.app.ReminderApp._update_restart_failed, fake)
        fake._poll_update_installation = MethodType(self.app.ReminderApp._poll_update_installation, fake)
        results = queue.Queue()
        results.put(("restart", False, RELEASE, installed))
        with patch.object(self.app, "restart_updated_app", side_effect=self.app.UpdateInstallError("failed")), patch.object(
            self.app, "rollback_update"
        ) as rollback, patch.object(self.app, "cleanup_update") as cleanup:
            self.app.ReminderApp._poll_update_installation(fake, results)
        rollback.assert_called_once_with(installed)
        cleanup.assert_called_once_with(installed)
        self.assertFalse(fake._update_install_running)
        self.assertEqual(events, [("busy", False)])


if __name__ == "__main__":
    unittest.main()
