import ast
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, call, patch

from app_info import APP_AUTHOR, APP_COPYRIGHT, APP_NAME
from i18n import set_language
from test_database import load_headless_app
from ui_icons import ICON_NAMES, LABEL_ICONS, icon_name_for_label


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


class BrandingTests(unittest.TestCase):
    def test_product_identity(self):
        self.assertEqual(APP_NAME, "PayPamin Flow")
        self.assertEqual(APP_AUTHOR, "Rickard Längkvist")
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

    def test_windows_icon_contains_every_taskbar_and_tray_size(self):
        from PIL import Image

        with Image.open(ASSETS / "paypamin_flow.ico") as icon:
            self.assertEqual(
                set(icon.ico.sizes()),
                {(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)},
            )

    def test_svg_icon_has_accessible_product_title(self):
        root = ET.parse(ASSETS / "paypamin_flow.svg").getroot()
        title = root.find("{http://www.w3.org/2000/svg}title")
        description = root.find("{http://www.w3.org/2000/svg}desc")
        self.assertIsNotNone(title)
        self.assertEqual(title.text, APP_NAME)
        self.assertIn("fakturadokument", description.text)
        self.assertIn("bock", description.text)
        self.assertNotIn("python", ET.tostring(root, encoding="unicode").lower())

    def test_png_icons_retain_creator_and_copyright_metadata(self):
        from PIL import Image

        icons = sorted(ASSETS.rglob("*.png"))
        self.assertEqual(len(icons), 72)
        for path in icons:
            with self.subTest(icon=path.relative_to(ASSETS)), Image.open(path) as icon:
                self.assertEqual(icon.info.get("Title"), APP_NAME)
                self.assertEqual(icon.info.get("Author"), APP_AUTHOR)
                self.assertEqual(icon.info.get("Copyright"), APP_COPYRIGHT)

    def test_vector_masters_are_print_ready_and_font_free(self):
        """Every logo is self-contained: no <text>, no filters, no linked fonts."""
        for name in (
            "paypamin_flow.svg",
            "paypamin_flow_small.svg",
            "paypamin_flow_tiny.svg",
            "paypamin_logo.svg",
            "print/paypamin_logo_print.svg",
            "print/paypamin_logo_print_mono.svg",
        ):
            with self.subTest(svg=name):
                text = (ASSETS / name).read_text(encoding="utf-8")
                self.assertNotIn("<text", text)
                self.assertNotIn("font-family", text)
                self.assertNotIn("<filter", text)
                self.assertNotIn("xlink:href", text)
                self.assertIn("Copyright ©", text)
                self.assertIn(APP_AUTHOR, text)
                root = ET.fromstring(text)
                self.assertTrue(root.get("viewBox"))
                self.assertGreaterEqual(len(root), 2)

    def test_small_icon_variant_is_a_separate_simplified_master(self):
        small = (ASSETS / "paypamin_flow_small.svg").read_text(encoding="utf-8")
        large = (ASSETS / "paypamin_flow.svg").read_text(encoding="utf-8")
        tiny = (ASSETS / "paypamin_flow_tiny.svg").read_text(encoding="utf-8")
        self.assertEqual(len({small, large, tiny}), 3)
        # Every master is flat: a gradient turns muddy in a 16 px tray icon
        # and complicates print, so every colour is a single ink.
        for text in (small, large, tiny):
            self.assertNotIn("linearGradient", text)
            self.assertNotIn("url(#", text)
        # The 24-40 px variant uses a thicker stroke and a larger badge, and the
        # 16 px variant drops the badge entirely so the P stays a P.
        self.assertIn('stroke-width="84"', small)
        # The badge must sit inside the rounded corner, otherwise its circle
        # pokes out of the silhouette and gains a dark fringe at 32 px.
        self.assertIn('r="100"', small)
        self.assertIn('rx="112"', small)
        self.assertIn('stroke-width="98"', tiny)
        self.assertNotIn("<circle", tiny)
        self.assertIn('stroke-width="66"', large)
        self.assertIn('r="104"', large)

    def test_small_icons_have_no_grey_halo_at_tray_sizes(self):
        """Partial-alpha edge pixels must carry the icon's own colour.

        Downsampling straight RGBA blends the transparent black around the
        artwork into the edge, which is what made 16-32 px icons look muddy.
        """
        from PIL import Image

        for name, size in (("paypamin_flow_16.png", 16), ("paypamin_flow_32.png", 32)):
            with self.subTest(icon=name), Image.open(ASSETS / name) as image:
                pixels = image.convert("RGBA").load()
                for y in range(size):
                    for x in range(size):
                        red, green, blue, alpha = pixels[x, y]
                        if 8 < alpha < 248:
                            # Blue-dominant and never near-black: the halo
                            # would show up as a desaturated grey pixel here.
                            self.assertGreater(max(red, green, blue), 20)
                            self.assertGreaterEqual(blue, red)

    def test_print_lockups_have_flat_ink_and_no_transparency(self):
        from PIL import Image

        for name in ("print/paypamin_logo_print.png", "print/paypamin_logo_print_mono.png"):
            with self.subTest(image=name), Image.open(ASSETS / name) as image:
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.size, (2400, 402))
                # White paper at the edges proves the artwork is on paper.
                self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
                self.assertEqual(image.getpixel((2399, 0)), (255, 255, 255))

        mono = (ASSETS / "print" / "paypamin_logo_print_mono.svg").read_text(encoding="utf-8")
        self.assertIn('fill="#000000"', mono)
        # One ink only: no brand navy or teal may survive in the mono lockup.
        self.assertNotIn("#0B2447", mono)
        self.assertNotIn("#0E8C82", mono)

    def test_print_pdfs_are_vector_and_sized_for_a_printer(self):
        import pymupdf

        for name in ("paypamin_logo_print.pdf", "paypamin_logo_print_mono.pdf"):
            with self.subTest(pdf=name):
                with pymupdf.open(ASSETS / "print" / name) as document:
                    self.assertEqual(document.page_count, 1)
                    page = document[0]
                    self.assertEqual(page.get_images(), [])
                    self.assertGreater(len(page.get_drawings()), 0)
                    # 90 mm artwork plus 4 mm clear space on every side. The
                    # lockup is cropped to the art (788.33:132), so the page is
                    # 98 x 23 mm instead of the old padded 98 x 29.9 mm.
                    self.assertAlmostEqual(page.rect.width / 72 * 25.4, 98.0, delta=0.5)
                    self.assertAlmostEqual(page.rect.height / 72 * 25.4, 23.1, delta=0.5)
                    self.assertIn(APP_AUTHOR, document.metadata.get("author", ""))

    def test_print_folder_is_self_contained_and_documented(self):
        print_dir = ASSETS / "print"
        expected = {
            "paypamin_logo_print.svg", "paypamin_logo_print_mono.svg",
            "paypamin_logo_print.pdf", "paypamin_logo_print_mono.pdf",
            "paypamin_logo_print.png", "paypamin_logo_print_mono.png",
            "README.txt",
        }
        self.assertEqual({path.name for path in print_dir.iterdir()}, expected)
        instructions = (print_dir / "README.txt").read_text(encoding="utf-8")
        self.assertIn(APP_AUTHOR, instructions)
        self.assertIn("90 mm", instructions)
        self.assertIn("assets/print", instructions)

    def test_horizontal_logo_has_vector_raster_and_creator_metadata(self):
        from PIL import Image

        root = ET.parse(ASSETS / "paypamin_logo.svg").getroot()
        self.assertEqual(root.find("{http://www.w3.org/2000/svg}title").text, "PayPamin Flow logotyp")
        self.assertIn(APP_AUTHOR, ET.tostring(root, encoding="unicode"))
        with Image.open(ASSETS / "paypamin_logo.png") as logo:
            # The header lockup keeps the artwork's own 788.33:132 ratio; a
            # rounded, stretched height makes the wordmark look soft. The
            # viewBox is cropped to the art, so no dead space is rendered.
            self.assertEqual(logo.size, (256, 43))
            self.assertAlmostEqual(logo.size[0] / logo.size[1], 788.33 / 132, places=1)
            self.assertEqual(logo.info.get("Title"), APP_NAME)
            self.assertEqual(logo.info.get("Author"), APP_AUTHOR)
            self.assertEqual(logo.info.get("Copyright"), APP_COPYRIGHT)

    def test_every_action_icon_has_normal_and_light_transparent_versions(self):
        from PIL import Image

        self.assertGreaterEqual(len(ICON_NAMES), 30)
        for name in ICON_NAMES:
            for suffix in ("", "_light"):
                with self.subTest(icon=name, variant=suffix), Image.open(ASSETS / "icons" / f"{name}{suffix}.png") as icon:
                    self.assertEqual(icon.size, (16, 16))
                    self.assertEqual(icon.mode, "RGBA")
                    self.assertEqual(icon.info.get("Author"), APP_AUTHOR)
                    alpha = icon.getchannel("A")
                    minimum, maximum = alpha.getextrema()
                    self.assertEqual(minimum, 0)
                    self.assertGreater(maximum, 240)

    def test_action_labels_resolve_in_both_languages(self):
        try:
            for language in ("sv", "en"):
                set_language(language)
                for source, expected in LABEL_ICONS.items():
                    with self.subTest(language=language, label=source):
                        self.assertEqual(icon_name_for_label(self.app_translation(source)), expected)
                self.assertEqual(icon_name_for_label(self.app_translation("Om {app_name}", app_name=APP_NAME)), "info")
                for level in ("P1", "P2"):
                    self.assertEqual(icon_name_for_label(self.app_translation("Spara och skriv om {level}", level=level)), "save")
        finally:
            set_language("sv")

    @staticmethod
    def app_translation(source, **values):
        from i18n import _
        return _(source, **values)

    def test_menu_and_button_renderers_do_not_resolve_action_icons(self):
        tree = ast.parse((ROOT / "paypamin_flow.py").read_text(encoding="utf-8"))
        app_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ReminderApp")
        methods = {node.name: node for node in app_class.body if isinstance(node, ast.FunctionDef)}
        for name in ("_apply_menu_icons", "_apply_action_icons"):
            with self.subTest(renderer=name):
                calls = list(ast.walk(methods[name]))
                self.assertFalse(any(
                    isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "icon_name_for_label"
                    for node in calls
                ))
                self.assertFalse(any(
                    isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "_ui_icon"
                    for node in calls
                ))

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
        window.after_idle.assert_called_once()

    def test_mapped_toplevel_reapplies_icon_before_action_finalization(self):
        window = Mock()
        fake = SimpleNamespace(_set_window_icon=Mock(), _finalize_window_actions=Mock())

        self.app.ReminderApp._finalize_toplevel(fake, window)

        self.assertEqual(fake._set_window_icon.call_args_list, [call(window)])
        self.assertEqual(fake._finalize_window_actions.call_args_list, [call(window)])

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
            after_idle=Mock(),
        )
        with patch.object(self.app.sys, "platform", "win32"), patch.object(
            self.app, "ICON_DIR", ASSETS
        ), patch.object(self.app.tk, "PhotoImage", create=True, side_effect=lambda **_kwargs: Mock()), patch.object(
            self.app, "configure_windows_window_icon", return_value=True
        ) as native_icon:
            self.app.ReminderApp._configure_icons(fake)
            fake.after_idle.call_args.args[0]()

        fake.iconphoto.assert_called_once()
        fake.iconbitmap.assert_called_once_with(default=str(ASSETS / "paypamin_flow.ico"))
        self.assertEqual(native_icon.call_args_list[0], call(fake))
        fake.after_idle.assert_called_once()
        self.assertEqual(native_icon.call_args_list, [call(fake), call(fake)])
        self.assertEqual(len(fake._window_icons), 4)
        self.assertIsNotNone(fake._brand_logo)
        self.assertEqual(fake._action_icons, {})

    def test_action_icons_are_cached_with_light_variant(self):
        fake = SimpleNamespace(_action_icons={})
        normal, light = Mock(), Mock()
        with patch.object(self.app, "ICON_DIR", ASSETS), patch.object(
            self.app.tk, "PhotoImage", create=True, side_effect=[normal, light]
        ) as photo:
            self.assertIs(self.app.ReminderApp._ui_icon(fake, "save"), normal)
            self.assertIs(self.app.ReminderApp._ui_icon(fake, "save"), normal)
            self.assertIs(self.app.ReminderApp._ui_icon(fake, "save", inverse=True), light)
        self.assertEqual(photo.call_count, 2)
        self.assertEqual(Path(photo.call_args_list[0].kwargs["file"]).name, "save.png")
        self.assertEqual(Path(photo.call_args_list[1].kwargs["file"]).name, "save_light.png")

    def test_buttons_are_recursively_text_only_without_loading_icons(self):
        fake = SimpleNamespace()
        fake._apply_action_icons = MethodType(self.app.ReminderApp._apply_action_icons, fake)
        button = Mock()
        button.winfo_class.return_value = "TButton"
        button.winfo_children.return_value = []
        root = Mock()
        root.winfo_class.return_value = "TFrame"
        root.winfo_children.return_value = [button]
        with patch.object(self.app.tk, "PhotoImage", create=True) as photo:
            self.app.ReminderApp._apply_action_icons(fake, root)
        button.configure.assert_called_once_with(image="", compound="none")
        photo.assert_not_called()

    def test_menu_commands_and_cascades_are_text_only(self):
        fake = SimpleNamespace()
        menu = Mock()
        menu.index.return_value = 1
        menu.type.side_effect = ["command", "cascade"]
        with patch.object(self.app.tk, "PhotoImage", create=True) as photo:
            self.app.ReminderApp._apply_menu_icons(fake, menu)
        self.assertEqual(menu.entryconfigure.call_count, 2)
        for call_args in menu.entryconfigure.call_args_list:
            self.assertEqual(call_args.kwargs, {"image": "", "compound": "none"})
        photo.assert_not_called()


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
    def native_ctypes(load_image, send_message, get_metrics, get_ancestor):
        return SimpleNamespace(
            windll=SimpleNamespace(user32=SimpleNamespace(
                LoadImageW=load_image,
                SendMessageW=send_message,
                GetSystemMetrics=get_metrics,
                GetAncestor=get_ancestor,
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
            get_ancestor = Mock(return_value=9000)
            fake_ctypes = self.native_ctypes(load_image, send_message, get_metrics, get_ancestor)
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
                    call(9000, 0x0080, 0, 1001),
                    call(9000, 0x0080, 1, 1002),
                    call(9000, 0x0080, 0, 1001),
                    call(9000, 0x0080, 1, 1002),
                ])
                self.assertEqual(get_ancestor.call_args_list, [call(4242, 2), call(4242, 3), call(4242, 2), call(4242, 3)])
                self.assertEqual(len(app._WINDOWS_NATIVE_ICONS), 2)
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()

    def test_native_icons_are_sent_to_distinct_root_and_owner_windows(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = load_headless_app(Path(temporary_directory))
            load_image = Mock(side_effect=[1001, 1002])
            send_message = Mock(return_value=0)
            get_metrics = Mock(side_effect=lambda index: 16 if index in (49, 50) else 32)
            get_ancestor = Mock(side_effect=[9000, 9001])
            fake_ctypes = self.native_ctypes(load_image, send_message, get_metrics, get_ancestor)
            window = Mock()
            window.winfo_id.return_value = 4242
            try:
                with patch.object(app.sys, "platform", "win32"), patch.dict(
                    sys.modules, {"ctypes": fake_ctypes}
                ), patch.object(app, "ICON_DIR", ASSETS):
                    self.assertTrue(app.configure_windows_window_icon(window))
                self.assertEqual(send_message.call_args_list, [
                    call(9000, 0x0080, 0, 1001), call(9000, 0x0080, 1, 1002),
                    call(9001, 0x0080, 0, 1001), call(9001, 0x0080, 1, 1002),
                ])
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
            get_ancestor = Mock(return_value=9000)
            fake_ctypes = self.native_ctypes(load_image, send_message, get_metrics, get_ancestor)
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
