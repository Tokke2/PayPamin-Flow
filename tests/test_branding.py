import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from app_info import APP_AUTHOR, APP_COPYRIGHT, APP_NAME, APP_VERSION


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


class BrandingTests(unittest.TestCase):
    def test_product_identity(self):
        self.assertEqual(APP_NAME, "PayPamin Flow")
        self.assertEqual(APP_AUTHOR, "Rickard Länkvist")
        self.assertIn(APP_AUTHOR, APP_COPYRIGHT)
        self.assertIn("Copyright ©", APP_COPYRIGHT)

    def test_windows_metadata_matches_application_version(self):
        major, minor, patch = (int(part) for part in APP_VERSION.split("."))
        metadata = (ROOT / "packaging" / "windows_version_info.txt").read_text(encoding="utf-8")
        self.assertIn(f"filevers=({major}, {minor}, {patch}, 0)", metadata)
        self.assertIn(f"prodvers=({major}, {minor}, {patch}, 0)", metadata)
        self.assertIn(f"StringStruct('FileVersion', '{APP_VERSION}')", metadata)
        self.assertIn(f"StringStruct('ProductVersion', '{APP_VERSION}')", metadata)

    def test_all_native_icon_formats_are_present(self):
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


if __name__ == "__main__":
    unittest.main()
