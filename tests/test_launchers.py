import configparser
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ConsoleFreeLauncherTests(unittest.TestCase):
    def test_windows_manual_launcher_is_hidden_and_uses_pythonw(self):
        launcher = (ROOT / "start_paypamin_flow.vbs").read_text(encoding="utf-8")
        self.assertIn("pythonw.exe", launcher)
        self.assertIn("paypamin_flow.pyw", launcher)
        self.assertIn("sh.Run cmd, 0, False", launcher)

    def test_macos_uses_pyw_instead_of_terminal_command_launcher(self):
        self.assertTrue((ROOT / "paypamin_flow.pyw").is_file())
        self.assertFalse((ROOT / "start_paypamin_flow.command").exists())

    def test_linux_menu_launcher_does_not_open_terminal(self):
        parser = configparser.ConfigParser()
        parser.optionxform = str
        parser.read(ROOT / "packaging" / "paypamin-flow.desktop", encoding="utf-8")
        self.assertEqual(parser["Desktop Entry"]["Terminal"], "false")
        self.assertEqual(parser["Desktop Entry"]["Exec"], "paypamin-flow")
        installer = (ROOT / "packaging" / "install_linux.sh").read_text(encoding="utf-8")
        self.assertIn("paypamin_flow.py", installer)
        self.assertNotIn("pyinstaller", installer.lower())

    def test_native_build_definitions_are_not_shipped(self):
        self.assertFalse((ROOT / "paypamin_flow.spec").exists())
        self.assertFalse((ROOT / "requirements-build.txt").exists())
        self.assertFalse((ROOT / "packaging" / "windows_version_info.txt").exists())


if __name__ == "__main__":
    unittest.main()
