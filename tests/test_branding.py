import ast
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app_info import APP_AUTHOR, APP_COPYRIGHT, APP_NAME
from test_database import load_headless_app


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


class BrandingTests(unittest.TestCase):
    def test_product_identity(self):
        self.assertEqual(APP_NAME, "PayPamin Flow")
        self.assertEqual(APP_AUTHOR, "Rickard Länkvist")
        self.assertIn(APP_AUTHOR, APP_COPYRIGHT)
        self.assertIn("Copyright ©", APP_COPYRIGHT)

    def test_all_desktop_icon_formats_are_present(self):
        expected_sizes = {
            "paypamin_flow.png": (256, 256),
            "paypamin_flow_16.png": (16, 16),
            "paypamin_flow_32.png": (32, 32),
            "paypamin_flow_48.png": (48, 48),
            "paypamin_flow_256.png": (256, 256),
            "paypamin_flow_512.png": (512, 512),
        }
        for filename, (width, height) in expected_sizes.items():
            with self.subTest(icon=filename):
                content = (ASSETS / filename).read_bytes()
                self.assertTrue(content.startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertEqual(int.from_bytes(content[16:20], "big"), width)
                self.assertEqual(int.from_bytes(content[20:24], "big"), height)
        self.assertTrue((ASSETS / "paypamin_flow.ico").read_bytes().startswith(b"\x00\x00\x01\x00"))
        self.assertTrue((ASSETS / "paypamin_flow.icns").read_bytes().startswith(b"icns"))

    def test_svg_icon_has_accessible_product_title(self):
        root = ET.parse(ASSETS / "paypamin_flow.svg").getroot()
        title = root.find("{http://www.w3.org/2000/svg}title")
        self.assertIsNotNone(title)
        self.assertEqual(title.text, APP_NAME)

    def test_every_secondary_window_uses_the_shared_icon_factory(self):
        tree = ast.parse((ROOT / "paypamin_flow.py").read_text(encoding="utf-8"))
        app_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ReminderApp")
        methods = {node.name: node for node in app_class.body if isinstance(node, ast.FunctionDef)}
        raw_toplevel_creators = set()
        for name, method in methods.items():
            for node in ast.walk(method):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "Toplevel":
                    raw_toplevel_creators.add(name)
        self.assertEqual(raw_toplevel_creators, {"_new_toplevel"})
        expected = {"show_about", "show_update_available", "check_python_addons", "preview_invoice", "invoice_dialog", "edit_p1", "settings"}
        for name in expected:
            with self.subTest(window=name):
                calls = [node for node in ast.walk(methods[name]) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "_new_toplevel"]
                self.assertTrue(calls)


class WindowIconTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = load_headless_app(Path(self.temporary.name))

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def test_shared_toplevel_factory_sets_title_parent_and_icon(self):
        window = Mock()
        fake = SimpleNamespace(_set_window_icon=Mock())
        with patch.object(self.app.tk, "Toplevel", create=True, return_value=window):
            result = self.app.ReminderApp._new_toplevel(fake, "PDF-granskning")
        self.assertIs(result, window)
        window.title.assert_called_once_with("PDF-granskning")
        window.transient.assert_called_once_with(fake)
        fake._set_window_icon.assert_called_once_with(window)

    def test_secondary_window_receives_all_png_icons(self):
        icons = [Mock(), Mock()]
        window = Mock()
        fake = SimpleNamespace(_window_icons=icons)
        with patch.object(self.app.sys, "platform", "linux"):
            self.app.ReminderApp._set_window_icon(fake, window)
        window.iconphoto.assert_called_once_with(False, *icons)
        window.iconbitmap.assert_not_called()

    def test_windows_secondary_window_also_receives_native_icon(self):
        window = Mock()
        fake = SimpleNamespace(_window_icons=[Mock()])
        with patch.object(self.app.sys, "platform", "win32"), patch.object(self.app, "ICON_DIR", ASSETS):
            self.app.ReminderApp._set_window_icon(fake, window)
        window.iconphoto.assert_called_once()
        window.iconbitmap.assert_called_once_with(str(ASSETS / "paypamin_flow.ico"))


class WindowsBrandingTests(unittest.TestCase):
    def test_pythonw_receives_product_taskbar_identity(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = load_headless_app(Path(temporary_directory))
            set_app_id = Mock(return_value=0)
            fake_ctypes = SimpleNamespace(
                windll=SimpleNamespace(
                    shell32=SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=set_app_id)
                ),
                c_wchar_p="wchar",
                c_long="long",
            )
            try:
                with patch.object(app.sys, "platform", "win32"), patch.dict(
                    sys.modules, {"ctypes": fake_ctypes}
                ):
                    app.configure_windows_app_identity()
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()
            set_app_id.assert_called_once_with(app.APP_ID)
            self.assertEqual(set_app_id.argtypes, ["wchar"])
            self.assertEqual(set_app_id.restype, "long")


if __name__ == "__main__":
    unittest.main()
