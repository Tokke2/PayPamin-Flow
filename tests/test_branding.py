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
