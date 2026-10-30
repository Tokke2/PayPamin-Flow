import configparser
import runpy
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class ConsoleFreeLauncherTests(unittest.TestCase):
    def test_windows_manual_launcher_is_hidden_and_uses_pythonw(self):
        launcher = (ROOT / "start_paypamin_flow.vbs").read_text(encoding="utf-8")
        self.assertIn("pythonw.exe", launcher)
        self.assertIn("paypamin_flow_launcher.py", launcher)
        self.assertIn("sh.Run cmd, 0, False", launcher)

    def test_pyw_compatibility_entrypoint_remains_without_terminal_launcher(self):
        compatibility = ROOT / "paypamin_flow.pyw"
        self.assertTrue(compatibility.is_file())
        self.assertIn("from paypamin_flow_launcher import run", compatibility.read_text(encoding="utf-8"))
        self.assertFalse((ROOT / "start_paypamin_flow.command").exists())

    def test_linux_menu_launcher_does_not_open_terminal(self):
        parser = configparser.ConfigParser()
        parser.optionxform = str
        parser.read(ROOT / "packaging" / "paypamin-flow.desktop", encoding="utf-8")
        self.assertEqual(parser["Desktop Entry"]["Terminal"], "false")
        self.assertEqual(parser["Desktop Entry"]["Exec"], "paypamin-flow")
        installer = (ROOT / "packaging" / "install_linux.sh").read_text(encoding="utf-8")
        self.assertIn("paypamin_flow_launcher.py", installer)
        self.assertNotIn("pyinstaller", installer.lower())
        shell_launcher = (ROOT / "start_paypamin_flow.sh").read_text(encoding="utf-8")
        self.assertIn("paypamin_flow_launcher.py", shell_launcher)

    def test_native_build_definitions_are_not_shipped(self):
        self.assertFalse((ROOT / "paypamin_flow.spec").exists())
        self.assertFalse((ROOT / "requirements-build.txt").exists())
        self.assertFalse((ROOT / "packaging" / "windows_version_info.txt").exists())

    def test_legacy_duplicate_entrypoints_are_removed(self):
        self.assertFalse((ROOT / "paypaminn_flow.py").exists())
        self.assertFalse((ROOT / "paypaminn_flow.pyw").exists())

    @staticmethod
    def load_gui_launcher():
        return runpy.run_path(str(ROOT / "paypamin_flow_launcher.py"), run_name="paypamin_flow_launcher_test")

    def test_gui_launcher_delegates_to_application_main(self):
        launcher = self.load_gui_launcher()
        calls = []
        fake_app = types.ModuleType("paypamin_flow")
        fake_app.main = lambda: calls.append("main")
        launcher["run"].__globals__["_report_startup_failure"] = lambda details: self.fail(details)
        with patch.dict(sys.modules, {"paypamin_flow": fake_app}):
            self.assertEqual(launcher["run"](), 0)
        self.assertEqual(calls, ["main"])

    def test_gui_launcher_logs_and_reports_import_failure_without_tkinter(self):
        launcher = self.load_gui_launcher()
        messages = []
        launcher["run"].__globals__["_show_startup_error"] = lambda message: messages.append(message) or True
        with tempfile.TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory)
            with patch.object(Path, "home", return_value=home), patch.dict(sys.modules, {"paypamin_flow": None}):
                self.assertEqual(launcher["run"](), 1)
            log_path = home / ".paminnelseapp" / "startup.log"
            self.assertTrue(log_path.is_file())
            self.assertIn("paypamin_flow", log_path.read_text(encoding="utf-8"))
        self.assertEqual(len(messages), 1)
        self.assertIn("could not start", messages[0])
        self.assertIn("Tkinter", messages[0])


if __name__ == "__main__":
    unittest.main()
