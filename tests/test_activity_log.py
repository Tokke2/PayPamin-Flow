import json
import tempfile
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace

from activity_log import ACTIVITY_LOGGER_NAME, instrument_action, instrument_tk_command
from test_database import load_headless_app


def events(records):
    return [
        json.loads(record.getMessage().split("Activity: ", 1)[1])
        for record in records
        if record.getMessage().startswith("Activity: ")
    ]


class ActivityLogTests(unittest.TestCase):
    def test_python_action_logs_start_and_completion_with_matching_id(self):
        with self.assertLogs(ACTIVITY_LOGGER_NAME, level="INFO") as captured:
            traced = instrument_action(lambda: "result", "Spara")
            self.assertIs(traced, instrument_action(traced, "Spara"))
            self.assertEqual(traced(), "result")

        payload = events(captured.records)
        self.assertEqual([event["status"] for event in payload], ["started", "completed"])
        self.assertEqual(payload[0]["details"]["action_id"], payload[1]["details"]["action_id"])
        self.assertEqual(payload[1]["details"]["result_type"], "str")
        self.assertGreaterEqual(payload[1]["details"]["duration_ms"], 0)
        self.assertTrue(all(event["session_id"] for event in payload))
        self.assertTrue(all(event["timestamp"] for event in payload))

    def test_registered_tk_command_failure_is_logged_and_reraised(self):
        class FakeTk:
            def __init__(self):
                self.commands = []

            def call(self, command):
                self.commands.append(command)
                raise RuntimeError("synthetic action failure")

        owner = SimpleNamespace(tk=FakeTk())
        traced = instrument_tk_command(owner, "registered-command", "Ta bort vald")
        with self.assertLogs(ACTIVITY_LOGGER_NAME, level="INFO") as captured:
            with self.assertRaisesRegex(RuntimeError, "synthetic action failure"):
                traced()

        self.assertEqual(owner.tk.commands, ["registered-command"])
        payload = events(captured.records)
        self.assertEqual([event["status"] for event in payload], ["started", "error"])
        self.assertEqual(payload[1]["details"]["error_type"], "RuntimeError")
        self.assertEqual(payload[1]["details"]["error"], "synthetic action failure")
        self.assertEqual(payload[0]["details"]["action_id"], payload[1]["details"]["action_id"])


class FakeTk:
    def __init__(self):
        self.commands = []

    def call(self, command):
        self.commands.append(command)
        return "registered-result"


class FakeButton:
    def __init__(self):
        self.tk = FakeTk()
        self.options = {"text": "Spara", "command": "save-command"}
        self.configure_calls = []

    def winfo_class(self):
        return "TButton"

    def winfo_children(self):
        return []

    def cget(self, key):
        return self.options[key]

    def configure(self, **options):
        self.configure_calls.append(options)
        self.options.update(options)


class FakeFrame:
    def __init__(self, children):
        self.children = children

    def winfo_class(self):
        return "TFrame"

    def winfo_children(self):
        return self.children


class FakeMenu:
    def __init__(self):
        self.tk = FakeTk()
        self.command = "menu-command"
        self.configure_calls = []

    def index(self, _value):
        return 0

    def type(self, _index):
        return "command"

    def entrycget(self, _index, key):
        return {"label": "Uppdatera appen", "command": self.command}[key]

    def entryconfigure(self, _index, **options):
        self.configure_calls.append(options)
        self.command = options["command"]


class ActivityWidgetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = load_headless_app(Path(self.temporary.name))

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def test_unhandled_tk_callback_exception_is_retained(self):
        try:
            raise ValueError("synthetic Tk failure")
        except ValueError as exc:
            with self.assertLogs(ACTIVITY_LOGGER_NAME, level="INFO") as captured:
                self.app.ReminderApp.report_callback_exception(
                    SimpleNamespace(), type(exc), exc, exc.__traceback__,
                )

        payload = events(captured.records)
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["status"], "error")
        self.assertEqual(payload[0]["action"], "unhandled_callback_exception")
        self.assertEqual(payload[0]["details"]["error_type"], "ValueError")

    def test_button_tree_is_instrumented_once_and_retains_tk_command(self):
        button = FakeButton()
        root = FakeFrame([button])
        fake = SimpleNamespace()
        fake._instrument_action_tree = MethodType(self.app.ReminderApp._instrument_action_tree, fake)

        fake._instrument_action_tree(root)
        fake._instrument_action_tree(root)
        self.assertEqual(len(button.configure_calls), 1)
        with self.assertLogs(ACTIVITY_LOGGER_NAME, level="INFO") as captured:
            result = button.options["command"]()

        self.assertEqual(result, "registered-result")
        self.assertEqual(button.tk.commands, ["save-command"])
        self.assertEqual([event["status"] for event in events(captured.records)], ["started", "completed"])

    def test_menu_is_instrumented_once_and_retains_tk_command(self):
        menu = FakeMenu()
        fake = SimpleNamespace()

        self.app.ReminderApp._instrument_menu_actions(fake, menu)
        self.app.ReminderApp._instrument_menu_actions(fake, menu)
        self.assertEqual(len(menu.configure_calls), 1)
        with self.assertLogs(ACTIVITY_LOGGER_NAME, level="INFO") as captured:
            result = menu.command()

        self.assertEqual(result, "registered-result")
        self.assertEqual(menu.tk.commands, ["menu-command"])
        payload = events(captured.records)
        self.assertEqual([event["component"] for event in payload], ["menu", "menu"])
        self.assertEqual([event["action"] for event in payload], ["Uppdatera appen", "Uppdatera appen"])


if __name__ == "__main__":
    unittest.main()
