import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
    def __init__(self, text, action, default=False):
        self.text = text
        self.action = action
        self.default = default


class FakeMenu:
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

    def controller(self, scheduled, opened, exited):
        return tray.TrayController(
            name="PayPamin Flow",
            identifier="paypamin-flow",
            icon_path=self.icon_path,
            scheduler=scheduled.append,
            on_open=lambda: opened.append(True),
            on_exit=lambda: exited.append(True),
            open_label=lambda: "Open",
            exit_label=lambda: "Exit",
        )

    def test_tray_actions_are_marshalled_to_tk_scheduler(self):
        scheduled, opened, exited = [], [], []
        controller = self.controller(scheduled, opened, exited)
        controller.start()
        icon = FakeIcon.instances[-1]
        self.assertTrue(icon.detached)
        self.assertTrue(icon.visible)
        self.assertFalse(icon.started)
        self.assertEqual(icon.menu.items[0].text(icon.menu.items[0]), "Open")
        self.assertEqual(icon.menu.items[1].text(icon.menu.items[1]), "Exit")
        icon.menu.items[0].action(icon, icon.menu.items[0])
        icon.menu.items[1].action(icon, icon.menu.items[1])
        self.assertEqual((opened, exited), ([], []))
        self.assertEqual(len(scheduled), 2)
        for callback in scheduled:
            callback()
        self.assertEqual((opened, exited), ([True], [True]))
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

    def test_explicit_exit_stops_tray_and_destroys_window(self):
        events = []
        fake = SimpleNamespace(
            _quitting=False,
            tray=SimpleNamespace(stop=lambda: events.append("tray stopped")),
            destroy=lambda: events.append("destroyed"),
        )
        self.app.ReminderApp.quit_app(fake)
        self.assertEqual(events, ["tray stopped", "destroyed"])
        self.assertTrue(fake._quitting)


if __name__ == "__main__":
    unittest.main()
