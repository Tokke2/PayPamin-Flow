import ast
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

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
        description = root.find("{http://www.w3.org/2000/svg}desc")
        self.assertIsNotNone(title)
        self.assertEqual(title.text, APP_NAME)
        self.assertIn("påminnelseklocka", description.text)
        self.assertNotIn("python", ET.tostring(root, encoding="unicode").lower())

    def test_png_icons_retain_creator_and_copyright_metadata(self):
        from PIL import Image

        for filename in ("paypamin_flow.png", "paypamin_flow_16.png", "paypamin_flow_512.png"):
            with self.subTest(icon=filename), Image.open(ASSETS / filename) as icon:
                self.assertEqual(icon.info.get("Title"), APP_NAME)
                self.assertEqual(icon.info.get("Author"), APP_AUTHOR)
                self.assertEqual(icon.info.get("Copyright"), APP_COPYRIGHT)

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
        expected = {"show_about", "show_update_available", "check_python_addons", "preview_invoice", "invoice_dialog", "edit_reminder", "preview_reminder_email", "settings"}
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
        with patch.object(self.app.sys, "platform", "win32"), patch.object(
            self.app, "ICON_DIR", ASSETS
        ), patch.object(self.app, "configure_windows_window_icon", return_value=True) as native_icon:
            self.app.ReminderApp._set_window_icon(fake, window)
        window.iconphoto.assert_called_once()
        window.iconbitmap.assert_called_once_with(str(ASSETS / "paypamin_flow.ico"))
        native_icon.assert_called_once_with(window)

    def test_main_window_uses_png_native_and_process_level_windows_icons(self):
        fake = SimpleNamespace(
            _configure_macos_dock_icon=Mock(),
            iconphoto=Mock(),
            iconbitmap=Mock(),
        )
        with patch.object(self.app.sys, "platform", "win32"), patch.object(
            self.app, "ICON_DIR", ASSETS
        ), patch.object(self.app.tk, "PhotoImage", create=True, side_effect=lambda **_kwargs: Mock()), patch.object(
            self.app, "configure_windows_window_icon", return_value=True
        ) as native_icon:
            self.app.ReminderApp._configure_icons(fake)

        fake.iconphoto.assert_called_once()
        fake.iconbitmap.assert_called_once_with(default=str(ASSETS / "paypamin_flow.ico"))
        native_icon.assert_called_once_with(fake)
        self.assertEqual(len(fake._window_icons), 4)


class MacOSBrandingTests(unittest.TestCase):
    def test_dock_uses_the_product_png(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = load_headless_app(Path(temporary_directory))
            try:
                image = Mock()
                image_class = Mock()
                image_class.alloc.return_value.initWithContentsOfFile_.return_value = image
                application = Mock()
                application_class = Mock()
                application_class.sharedApplication.return_value = application
                app_kit = SimpleNamespace(NSApplication=application_class, NSImage=image_class)
                with patch.object(app.sys, "platform", "darwin"), patch.dict(sys.modules, {"AppKit": app_kit}), patch.object(app, "ICON_DIR", ASSETS):
                    app.ReminderApp._configure_macos_dock_icon(SimpleNamespace())
                image_class.alloc.return_value.initWithContentsOfFile_.assert_called_once_with(str(ASSETS / "paypamin_flow_256.png"))
                application.setApplicationIconImage_.assert_called_once_with(image)
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()


class WindowsBrandingTests(unittest.TestCase):
    @staticmethod
    def native_ctypes(load_image, send_message, get_metrics):
        return SimpleNamespace(
            windll=SimpleNamespace(user32=SimpleNamespace(
                LoadImageW=load_image,
                SendMessageW=send_message,
                GetSystemMetrics=get_metrics,
            )),
            c_void_p="void-pointer",
            c_wchar_p="wide-string",
            c_uint="unsigned-int",
            c_int="int",
            c_size_t="size",
            c_ssize_t="signed-size",
        )

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

    def test_native_window_icons_cover_small_big_and_are_shared(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = load_headless_app(Path(temporary_directory))
            load_image = Mock(side_effect=[1001, 1002])
            send_message = Mock(return_value=0)
            sizes = {49: 16, 50: 16, 11: 32, 12: 32}
            get_metrics = Mock(side_effect=lambda index: sizes[index])
            fake_ctypes = self.native_ctypes(load_image, send_message, get_metrics)
            window = Mock()
            window.winfo_id.return_value = 4242
            try:
                with patch.object(app.sys, "platform", "win32"), patch.dict(
                    sys.modules, {"ctypes": fake_ctypes}
                ), patch.object(app, "ICON_DIR", ASSETS):
                    self.assertTrue(app.configure_windows_window_icon(window))
                    self.assertTrue(app.configure_windows_window_icon(window))

                icon_path = str((ASSETS / "paypamin_flow.ico").resolve())
                self.assertEqual(load_image.call_args_list, [
                    call(None, icon_path, 1, 16, 16, 0x0010),
                    call(None, icon_path, 1, 32, 32, 0x0010),
                ])
                self.assertEqual(send_message.call_args_list, [
                    call(4242, 0x0080, 0, 1001),
                    call(4242, 0x0080, 1, 1002),
                    call(4242, 0x0080, 0, 1001),
                    call(4242, 0x0080, 1, 1002),
                ])
                self.assertEqual(len(app._WINDOWS_NATIVE_ICONS), 2)
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()

    def test_native_window_icon_failure_is_safe_and_sends_nothing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = load_headless_app(Path(temporary_directory))
            load_image = Mock(return_value=0)
            send_message = Mock()
            get_metrics = Mock(return_value=32)
            fake_ctypes = self.native_ctypes(load_image, send_message, get_metrics)
            try:
                with patch.object(app.sys, "platform", "win32"), patch.dict(
                    sys.modules, {"ctypes": fake_ctypes}
                ), patch.object(app, "ICON_DIR", ASSETS):
                    self.assertFalse(app.configure_windows_window_icon(Mock()))
                send_message.assert_not_called()
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()


if __name__ == "__main__":
    unittest.main()
