import os
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import autostart
from app_info import APP_ID, APP_NAME, APP_SLUG


class AutostartTests(unittest.TestCase):
    def test_source_launch_command_uses_new_module_name(self):
        command = autostart.launch_command()
        self.assertGreaterEqual(len(command), 2)
        self.assertTrue(command[0])
        expected_script = "paypamin_flow.pyw" if sys.platform.startswith("win") else "paypamin_flow.py"
        self.assertTrue(command[1].endswith(expected_script))
        self.assertTrue(Path(command[1]).is_file())

    def test_linux_autostart_writes_and_removes_xdg_desktop_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            config = temp / "config"
            data = temp / "data"
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(config)}), \
                    mock.patch.object(autostart, "LOCAL_DATA_DIR", data), \
                    mock.patch.object(autostart.sys, "platform", "linux"):
                autostart.set_autostart(True)
                path = config / "autostart" / f"{APP_SLUG}.desktop"
                self.assertTrue(path.is_file())
                content = path.read_text(encoding="utf-8")
                self.assertIn("[Desktop Entry]", content)
                self.assertIn(f"Name={APP_NAME}", content)
                self.assertIn("paypamin_flow.py", content)
                self.assertIn("Terminal=false", content)
                self.assertIn("Comment=Local invoice and payment reminder app", content)
                self.assertIn("Comment[sv]=Lokal app för fakturor och betalningspåminnelser", content)
                self.assertIn("X-GNOME-Autostart-enabled=true", content)
                self.assertTrue((data / "paypamin_flow.png").is_file())
                self.assertTrue(autostart.is_autostart_enabled())

                autostart.set_autostart(False)
                self.assertFalse(path.exists())
                self.assertFalse(autostart.is_autostart_enabled())

    def test_windows_source_autostart_always_uses_pythonw(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source"
            source.mkdir()
            (source / "paypamin_flow.py").write_text("", encoding="utf-8")
            (source / "paypamin_flow.pyw").write_text("", encoding="utf-8")
            python = temp / "python.exe"
            pythonw = temp / "pythonw.exe"
            python.write_bytes(b"")
            pythonw.write_bytes(b"")
            with mock.patch.object(autostart.sys, "platform", "win32"), \
                    mock.patch.object(autostart.sys, "executable", str(python)), \
                    mock.patch.object(autostart, "SOURCE_DIR", source):
                command = autostart.launch_command()
                self.assertEqual(command, [str(pythonw.resolve()), str(source / "paypamin_flow.pyw")])
                pythonw.unlink()
                with self.assertRaises(autostart.AutostartError):
                    autostart.launch_command()

    def test_windows_autostart_writes_and_removes_current_user_run_value(self):
        values = {}
        fake_winreg = mock.MagicMock()
        fake_winreg.HKEY_CURRENT_USER = "HKCU"
        fake_winreg.KEY_SET_VALUE = 2
        fake_winreg.REG_SZ = 1
        key_context = mock.MagicMock()
        key_context.__enter__.return_value = key_context
        fake_winreg.OpenKey.return_value = key_context
        fake_winreg.CreateKeyEx.return_value = key_context
        fake_winreg.SetValueEx.side_effect = lambda key, name, reserved, kind, value: values.__setitem__(name, value)

        def query_value(key, name):
            if name not in values:
                raise FileNotFoundError(name)
            return values[name], fake_winreg.REG_SZ

        def delete_value(key, name):
            if name not in values:
                raise FileNotFoundError(name)
            del values[name]

        fake_winreg.QueryValueEx.side_effect = query_value
        fake_winreg.DeleteValue.side_effect = delete_value
        command = [r"C:\Python\pythonw.exe", r"C:\Pay Pamin\paypamin_flow.pyw"]
        with mock.patch.dict(sys.modules, {"winreg": fake_winreg}), \
                mock.patch.object(autostart.sys, "platform", "win32"), \
                mock.patch.object(autostart, "launch_command", return_value=command):
            autostart.set_autostart(True)
            self.assertIn(autostart.WINDOWS_VALUE_NAME, values)
            self.assertIn('"C:\\Pay Pamin\\paypamin_flow.pyw"', values[autostart.WINDOWS_VALUE_NAME])
            self.assertTrue(autostart.is_autostart_enabled())

            autostart.set_autostart(False)
            self.assertNotIn(autostart.WINDOWS_VALUE_NAME, values)
            self.assertFalse(autostart.is_autostart_enabled())

    def test_macos_autostart_writes_and_removes_launch_agent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            with mock.patch.object(autostart.Path, "home", return_value=home), \
                    mock.patch.object(autostart.sys, "platform", "darwin"):
                autostart.set_autostart(True)
                path = home / "Library" / "LaunchAgents" / f"{APP_ID}.plist"
                self.assertTrue(path.is_file())
                payload = plistlib.loads(path.read_bytes())
                self.assertEqual(payload["Label"], APP_ID)
                self.assertTrue(payload["RunAtLoad"])
                self.assertEqual(payload["LimitLoadToSessionType"], "Aqua")
                self.assertTrue(payload["ProgramArguments"][1].endswith("paypamin_flow.py"))
                self.assertTrue(autostart.is_autostart_enabled())

                autostart.set_autostart(False)
                self.assertFalse(path.exists())

    def test_desktop_arguments_escape_spaces_and_field_codes(self):
        quoted = autostart._desktop_argument('/tmp/Pay Pamin/100%/app')
        self.assertEqual(quoted, '"/tmp/Pay Pamin/100%%/app"')

    def test_unsupported_platform_does_not_claim_success(self):
        with mock.patch.object(autostart.sys, "platform", "freebsd14"):
            with self.assertRaises(autostart.AutostartError):
                autostart.set_autostart(True)
            self.assertFalse(autostart.is_autostart_enabled())


if __name__ == "__main__":
    unittest.main()
