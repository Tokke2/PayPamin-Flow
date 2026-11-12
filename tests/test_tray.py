import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import tray
from test_database import load_headless_app


class FakeImage:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def convert(self, mode):
        return self

    def copy(self):
        return object()


class FakeMenuItem:
    def __init__(self, text, action, default=False, enabled=True):
        self.text = text
        self.action = action
        self.default = default
        self.enabled = enabled


class FakeMenu:
    SEPARATOR = FakeMenuItem("- - - -", None)

    def __init__(self, *items):
        self.items = items


class FakeIcon:
    instances = []

    def __init__(self, identifier, image, name, menu):
        self.identifier = identifier
        self.name = name
        self.menu = menu
        self.started = False
        self.detached = False
        self.visible = False
        self.stopped = False
        self.refreshed = False
        self.instances.append(self)

    def run(self):
        self.started = True

    def run_detached(self, setup=None):
        self.detached = True
        if setup:
            setup(self)

    def stop(self):
        self.stopped = True

    def update_menu(self):
        self.refreshed = True

    def notify(self, message, title=None):
        self.notified = getattr(self, "notified", [])
        self.notified.append((title, message))


class TrayControllerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.icon_path = Path(self.temporary.name) / "icon.png"
        self.icon_path.write_bytes(b"image")
        self.fake_pystray = types.ModuleType("pystray")
        self.fake_pystray.Icon = FakeIcon
        self.fake_pystray.Menu = FakeMenu
        self.fake_pystray.MenuItem = FakeMenuItem
        fake_pil = types.ModuleType("PIL")
        fake_image_module = types.ModuleType("PIL.Image")
        fake_image_module.open = lambda path: FakeImage()
        fake_pil.Image = fake_image_module
        self.modules = patch.dict(
            sys.modules, {"pystray": self.fake_pystray, "PIL": fake_pil, "PIL.Image": fake_image_module}
        )
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def controller(self, scheduled, opened, exited, updated=None):
        if updated is None:
            updated = []
        return tray.TrayController(
            name="PayPamin Flow",
            identifier="paypamin-flow",
            icon_path=self.icon_path,
            scheduler=scheduled.append,
            on_open=lambda: opened.append(True),
            on_update=lambda: updated.append(True),
            on_exit=lambda: exited.append(True),
            open_label=lambda: "Open",
            update_label=lambda: "Update app",
            exit_label=lambda: "Exit",
        )

    def test_tray_actions_are_marshalled_to_tk_scheduler(self):
        scheduled, opened, updated, exited = [], [], [], []
        controller = self.controller(scheduled, opened, exited, updated)
        controller.start()
        icon = FakeIcon.instances[-1]
        self.assertTrue(icon.detached)
        self.assertTrue(icon.visible)
        self.assertFalse(icon.started)
        # Minimal controller: open, update, separator, exit.
        actions = [item for item in icon.menu.items if item.action is not None]
        self.assertEqual(
            [item.text(item) for item in actions],
            ["Open", "Update app", "Exit"],
        )
        for item in actions:
            item.action(icon, item)
        self.assertEqual((opened, updated, exited), ([], [], []))
        self.assertEqual(len(scheduled), 3)
        for callback in scheduled:
            callback()
        self.assertEqual((opened, updated, exited), ([True], [True], [True]))
        controller.refresh()
        self.assertTrue(icon.refreshed)
        controller.stop()
        self.assertTrue(icon.stopped)

    def test_visibility_failure_is_reported_through_tk_scheduler(self):
        scheduled = []
        errors = []
        controller = self.controller(scheduled, [], [])
        controller.on_error = errors.append

        class BrokenIcon:
            @property
            def visible(self):
                return False

            @visible.setter
            def visible(self, value):
                raise RuntimeError("native tray failed")

        controller._show_when_ready(BrokenIcon())
        self.assertEqual(errors, [])
        self.assertEqual(len(scheduled), 1)
        scheduled[0]()
        self.assertEqual(str(errors[0]), "native tray failed")


class TrayMenuAndNotificationTests(unittest.TestCase):
    """The richer tray menu, the tooltip and the optional balloon message."""

    setUp = TrayControllerTests.setUp
    controller = TrayControllerTests.controller

    def controller_with_extras(self, scheduled, opened, exited, *, status=None):
        controller = self.controller(scheduled, opened, exited)
        controller.on_scan = lambda: None
        controller.on_export = lambda: None
        controller.scan_label = lambda: "Scan now"
        controller.export_label = lambda: "Open export folder"
        controller.status_label = status or (lambda: "PayPamin Flow · 2 awaiting P1")
        return controller

    def test_menu_order_shows_status_open_scan_export_update_separator_exit(self):
        controller = self.controller_with_extras([], [], [])
        controller.start()
        menu = FakeIcon.instances[-1].menu

        labels = [
            "- - - -" if item is FakeMenu.SEPARATOR and not callable(item.text) else item.text(item)
            for item in menu.items
        ]
        self.assertEqual(
            labels,
            [
                "PayPamin Flow · 2 awaiting P1",
                "Open",
                "Scan now",
                "Open export folder",
                "Update app",
                "- - - -",
                "Exit",
            ],
        )
        # The status line is informational and must not look clickable.
        self.assertFalse(menu.items[0].enabled)
        # Opening the window stays the double-click default.
        self.assertTrue(menu.items[1].default)

    def test_status_line_keeps_working_when_the_label_fails(self):
        def broken():
            raise RuntimeError("no database")

        controller = self.controller_with_extras([], [], [], status=broken)
        controller.start()
        menu = FakeIcon.instances[-1].menu
        self.assertEqual(menu.items[0].text(menu.items[0]), "PayPamin Flow")

    def test_tray_notification_is_optional_and_never_raises(self):
        controller = self.controller([], [], [])
        self.assertFalse(controller.notify("hello"))
        controller.start()
        icon = FakeIcon.instances[-1]
        self.assertTrue(controller.notify("hello", "Title"))
        self.assertEqual(icon.notified, [("Title", "hello")])

        def broken_notify(*_args, **_kwargs):
            raise NotImplementedError("backend without balloons")

        icon.notify = broken_notify
        self.assertFalse(controller.notify("hello"))
        controller.set_title("PayPamin Flow · 3 awaiting P2")
        self.assertEqual(icon.name, "PayPamin Flow")
        self.assertEqual(icon.title, "PayPamin Flow · 3 awaiting P2")

    def test_unavailable_backend_explains_the_platform_remedy(self):
        import tray as tray_module

        with patch.object(tray_module.sys, "platform", "linux"):
            hint = tray_module.backend_hint(RuntimeError("no appindicator"))
        self.assertIn("AppIndicator", hint)
        self.assertIn("Wayland", hint)
        self.assertIn("no appindicator", hint)

        with patch.object(tray_module.sys, "platform", "win32"):
            self.assertIn("Windows", tray_module.backend_hint(RuntimeError("boom")))
        with patch.object(tray_module.sys, "platform", "darwin"):
            self.assertIn("macOS", tray_module.backend_hint(RuntimeError("boom")))

    def test_failed_start_reports_the_platform_hint_to_the_caller(self):
        controller = self.controller([], [], [])
        with patch.object(self.fake_pystray, "Icon", side_effect=OSError("no native tray")):
            with self.assertRaises(tray.TrayUnavailable) as raised:
                controller.start()
        self.assertIsInstance(raised.exception.hint, str)
        self.assertTrue(raised.exception.hint)
        self.assertIsNone(controller.icon)


class WindowCloseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = load_headless_app(Path(self.temporary.name))

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def test_close_hides_running_window_instead_of_destroying_it(self):
        events = []
        fake = SimpleNamespace(
            _quitting=False,
            tray=SimpleNamespace(running=True),
            withdraw=lambda: events.append("withdrawn"),
            destroy=lambda: events.append("destroyed"),
        )
        self.app.ReminderApp.hide_to_tray(fake)
        self.assertEqual(events, ["withdrawn"])

    def test_start_minimized_hides_a_working_tray_window(self):
        events = []
        fake = SimpleNamespace(
            _quitting=False,
            tray=SimpleNamespace(running=True),
            start_tray=Mock(),
            withdraw=lambda: events.append("withdrawn"),
        )

        self.assertTrue(self.app.ReminderApp.start_minimized(fake))

        fake.start_tray.assert_not_called()
        self.assertEqual(events, ["withdrawn"])

    def test_start_minimized_keeps_the_window_visible_without_a_tray(self):
        fake = SimpleNamespace(
            _quitting=False,
            tray=None,
            start_tray=lambda: None,
            withdraw=Mock(),
        )

        self.assertFalse(self.app.ReminderApp.start_minimized(fake))

        fake.withdraw.assert_not_called()

    def test_minimize_hides_main_window_to_system_tray(self):
        events = []
        fake = SimpleNamespace(
            _quitting=False,
            state=lambda: "iconic",
            hide_to_tray=lambda: events.append("hidden"),
        )
        self.app.ReminderApp._hide_minimized_window(fake)
        self.assertEqual(events, ["hidden"])

    def test_withdraw_does_not_retrigger_minimize_to_tray(self):
        events = []
        fake = SimpleNamespace(
            _quitting=False,
            state=lambda: "withdrawn",
            hide_to_tray=lambda: events.append("hidden"),
        )
        self.app.ReminderApp._hide_minimized_window(fake)
        self.assertEqual(events, [])

    def test_unmap_defers_state_check_for_main_window_only(self):
        scheduled = []
        callback = lambda: None
        fake = SimpleNamespace(_quitting=False, after_idle=scheduled.append, _hide_minimized_window=callback)
        self.app.ReminderApp._on_main_window_unmap(fake, SimpleNamespace(widget=fake))
        self.app.ReminderApp._on_main_window_unmap(fake, SimpleNamespace(widget=object()))
        self.assertEqual(scheduled, [callback])

    def test_tray_status_text_summarises_the_workload(self):
        import i18n

        fake = SimpleNamespace()
        rows = [
            {"ignored": 1, "paid": 0, "reviewed": 1, "p1_date": "", "p2_date": "",
             "due_date": "2020-01-01", "fee": "150", "amount": 1000},
        ]
        counts = self.app.ReminderApp._tray_counts_from_row(rows)
        self.assertEqual(counts, {"Ignorerad": 1})

        # An empty workload yields just the product name.
        self.app._tray_counts_from_row = staticmethod(lambda _rows: {})
        self.assertEqual(self.app.ReminderApp.tray_status_text(fake), "PayPamin Flow")

        # The English strings exist and interpolate the counts.
        i18n.set_language("en")
        try:
            self.assertEqual(i18n._("{count} väntar P1", count=2), "2 awaiting P1")
            self.assertEqual(i18n._("{count} väntar P2", count=1), "1 awaiting P2")
            self.assertEqual(i18n._("{count} att granska", count=3), "3 to review")
        finally:
            i18n.set_language("sv")

    def test_first_hide_explains_the_tray_only_once(self):
        from unittest.mock import patch as mock_patch

        notifications = []
        fake = SimpleNamespace(
            tray=SimpleNamespace(
                running=True,
                notify=lambda message, title=None: notifications.append((title, message)) or True,
            ),
        )
        with mock_patch.object(self.app, "setting", return_value="0"), mock_patch.object(
            self.app, "set_setting"
        ) as saved:
            self.app.ReminderApp._explain_tray_hide(fake)
        self.assertEqual(len(notifications), 1)
        self.assertIn("systemfältet", notifications[0][1])
        saved.assert_called_once_with("tray_hint_shown", "1")

        with mock_patch.object(self.app, "setting", return_value="1"), mock_patch.object(
            self.app, "set_setting"
        ) as saved_again:
            self.app.ReminderApp._explain_tray_hide(fake)
        self.assertEqual(len(notifications), 1)
        saved_again.assert_not_called()

    def test_minimized_window_is_restored_if_system_tray_is_unavailable(self):
        events = []
        fake = SimpleNamespace(
            _quitting=False,
            tray=SimpleNamespace(running=False),
            start_tray=lambda: None,
            state=lambda: "iconic",
            deiconify=lambda: events.append("shown"),
            quit_app=lambda: events.append("quit"),
        )
        with patch.object(self.app.messagebox, "askyesno", return_value=False, create=True):
            self.app.ReminderApp.hide_to_tray(fake)
        self.assertEqual(events, ["shown"])

    def test_show_from_tray_reapplies_windows_taskbar_icon(self):
        fake = SimpleNamespace(
            deiconify=Mock(), lift=Mock(), focus_force=Mock(), after_idle=Mock(),
            _maybe_show_ledger_reminder=Mock(),
        )
        with patch.object(self.app.sys, "platform", "win32"), patch.object(
            self.app, "configure_windows_window_icon", return_value=True
        ) as native_icon:
            self.app.ReminderApp.show_from_tray(fake)
            fake.after_idle.call_args_list[0].args[0]()

        self.assertEqual(fake.after_idle.call_count, 2)
        native_icon.assert_called_once_with(fake)
        self.assertIs(fake.after_idle.call_args_list[1].args[0], fake._maybe_show_ledger_reminder)

    def test_second_start_restores_the_existing_window(self):
        event = Mock()
        event.is_set.return_value = True
        fake = SimpleNamespace(
            _quitting=False,
            _single_instance_activation=event,
            _poll_single_instance_activation=Mock(),
            show_from_tray=Mock(),
            after=Mock(),
        )

        self.app.ReminderApp._poll_single_instance_activation(fake)

        event.clear.assert_called_once_with()
        fake.show_from_tray.assert_called_once_with()
        fake.after.assert_called_once_with(200, fake._poll_single_instance_activation)

    def test_update_child_claims_ownership_without_activating_old_app(self):
        instance = Mock()
        instance.try_acquire.return_value = True
        fake = SimpleNamespace(
            _quitting=False,
            _single_instance=instance,
            _poll_single_instance_activation=Mock(),
            quit_app=Mock(),
        )

        self.app.ReminderApp._claim_single_instance_after_update(fake, 0.0)

        instance.try_acquire.assert_called_once_with()
        fake._poll_single_instance_activation.assert_called_once_with()
        instance.activate_existing.assert_not_called()
        fake.quit_app.assert_not_called()

    def test_update_handoff_timeout_closes_duplicate_child(self):
        instance = Mock()
        instance.try_acquire.return_value = False
        instance.activate_existing.return_value = True
        fake = SimpleNamespace(
            _quitting=False,
            _single_instance=instance,
            quit_app=Mock(),
        )
        with patch.object(self.app.time, "monotonic", return_value=20.0):
            self.app.ReminderApp._claim_single_instance_after_update(fake, 0.0)

        instance.activate_existing.assert_called_once_with()
        fake.quit_app.assert_called_once_with()

    def test_tray_update_opens_window_and_starts_manual_check(self):
        events = []
        fake = SimpleNamespace(
            show_from_tray=lambda: events.append("shown"),
            check_for_updates=lambda manual: events.append(("manual", manual)),
        )

        self.app.ReminderApp.update_from_tray(fake)

        self.assertEqual(events, ["shown", ("manual", True)])

    def test_duplicate_main_start_returns_before_database_or_window_creation(self):
        instance = Mock()
        instance.acquire.return_value = False
        instance.activated_existing = True
        with patch.object(self.app, "SingleInstance", return_value=instance), patch.object(
            self.app, "configure_console_free_subprocesses"
        ), patch.object(self.app, "configure_windows_app_identity"), patch.object(
            self.app, "init_db"
        ) as init_db, patch.object(self.app, "ReminderApp") as window:
            self.app.main()

        instance.acquire.assert_called_once_with()
        init_db.assert_not_called()
        window.assert_not_called()
        instance.release.assert_called_once_with()

    def test_explicit_exit_stops_tray_and_destroys_window(self):
        events = []
        fake = SimpleNamespace(
            _quitting=False,
            _run_exit_cache_cleanup=lambda: events.append("cache cleaned"),
            tray=SimpleNamespace(stop=lambda: events.append("tray stopped")),
            destroy=lambda: events.append("destroyed"),
        )
        self.app.ReminderApp.quit_app(fake)
        self.assertEqual(events, ["cache cleaned", "tray stopped", "destroyed"])
        self.assertTrue(fake._quitting)


if __name__ == "__main__":
    unittest.main()
