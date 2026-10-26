import ast
import configparser
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ConsoleFreeLauncherTests(unittest.TestCase):
    def test_native_build_is_windowed_and_macos_uses_app_bundle(self):
        tree = ast.parse((ROOT / "paypamin_flow.spec").read_text(encoding="utf-8"))
        exe_calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "EXE"]
        self.assertEqual(len(exe_calls), 1)
        console = next(keyword.value for keyword in exe_calls[0].keywords if keyword.arg == "console")
        self.assertIsInstance(console, ast.Constant)
        self.assertFalse(console.value)
        self.assertTrue(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "BUNDLE" for node in ast.walk(tree)))

    def test_windows_manual_launcher_is_hidden_and_uses_pythonw(self):
        launcher = (ROOT / "start_paypamin_flow.vbs").read_text(encoding="utf-8")
        self.assertIn("pythonw.exe", launcher)
        self.assertIn("paypamin_flow.pyw", launcher)
        self.assertIn("sh.Run cmd, 0, False", launcher)

    def test_linux_menu_launcher_does_not_open_terminal(self):
        parser = configparser.ConfigParser()
        parser.optionxform = str
        parser.read(ROOT / "packaging" / "paypamin-flow.desktop", encoding="utf-8")
        self.assertEqual(parser["Desktop Entry"]["Terminal"], "false")
        self.assertEqual(parser["Desktop Entry"]["Exec"], "paypamin-flow")


if __name__ == "__main__":
    unittest.main()
