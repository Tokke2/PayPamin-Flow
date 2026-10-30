import os
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import autostart
from app_info import APP_ID, APP_NAME, APP_SLUG, MINIMIZED_START_ARG


class AutostartTests(unittest.TestCase):
    def test_source_launch_command_uses_shared_launcher(self):
        command = autostart.launch_command()
        self.assertGreaterEqual(len(command), 2)
        self.assertTrue(command[0])
        self.assertTrue(command[1].endswith("paypamin_flow_launcher.py"))
        self.assertTrue(Path(command[1]).is_file())
        self.assertNotIn(".pyw", command[1])
        self.assertEqual(command[2], MINIMIZED_START_ARG)

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
                self.assertIn("paypamin_flow_launcher.py", content)
                self.assertNotIn("paypamin_flow.pyw", content)
                self.assertIn("Terminal=false", content)
                self.assertIn("Comment=Local invoice and payment reminder app", content)
                self.assertIn("Comment[sv]=Lokal app för fakturor och betalningspåminnelser", content)
                self.assertIn("X-GNOME-Autostart-enabled=true", content)
                self.assertIn(f'"{MINIMIZED_START_ARG}"', content)
                self.assertTrue((data / "paypamin_flow.png").is_file())
                self.assertTrue(autostart.is_autostart_enabled())

                autostart.set_autostart(False)
                self.assertFalse(path.exists())
                self.assertFalse(autostart.is_autostart_enabled())

    def test_windows_source_autostart_uses_pythonw_without_pyw(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source"
            source.mkdir()
            launcher = source / "paypamin_flow_launcher.py"
            launcher.write_text("", encoding="utf-8")
            python = temp / "python.exe"
            pythonw = temp / "pythonw.exe"
            python.write_bytes(b"")
            pythonw.write_bytes(b"")
            with mock.patch.object(autostart.sys, "platform", "win32"), \
                    mock.patch.object(autostart.sys, "executable", str(python)), \
                    mock.patch.object(autostart, "SOURCE_DIR", source):
                command = autostart.launch_command()
                self.assertEqual(command, [str(pythonw.resolve()), str(launcher), MINIMIZED_START_ARG])
                self.assertFalse(any(part.endswith(".pyw") for part in command))
                pythonw.unlink()
                with self.assertRaises(autostart.AutostartError):
                    autostart.launch_command()

    def test_windows_autostart_creates_icon_shortcut_and_migrates_legacy_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source"
            source.mkdir()
            resource = temp / "resource"
            icon = resource / "assets" / "paypamin_flow.ico"
            icon.parent.mkdir(parents=True)
            icon.write_bytes(b"icon")
            powershell = temp / "Windows" / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
            powershell.parent.mkdir(parents=True)
            powershell.write_bytes(b"")
            pythonw = temp / "pythonw.exe"
            command = [str(pythonw), str(source / "paypamin_flow_launcher.py"), MINIMIZED_START_ARG]
            remove_legacy = mock.Mock()

            def create_shortcut(process_command, **kwargs):
                Path(kwargs["env"]["PAYPAMIN_FLOW_SHORTCUT"]).write_bytes(b"shortcut")
                return SimpleNamespace(returncode=0)

            with mock.patch.dict(os.environ, {"APPDATA": str(temp / "Roaming"), "SystemRoot": str(temp / "Windows")}), \
                    mock.patch.object(autostart.sys, "platform", "win32"), \
                    mock.patch.object(autostart, "SOURCE_DIR", source), \
                    mock.patch.object(autostart, "RESOURCE_DIR", resource), \
                    mock.patch.object(autostart, "launch_command", return_value=command), \
                    mock.patch.object(autostart, "_remove_legacy_windows_run_value", remove_legacy), \
                    mock.patch.object(autostart, "_legacy_windows_autostart_exists", return_value=False), \
                    mock.patch.object(autostart.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
                    mock.patch.object(autostart.subprocess, "run", side_effect=create_shortcut) as run:
                autostart.set_autostart(True)
                shortcut = autostart._windows_shortcut_path()
                self.assertEqual(shortcut.read_bytes(), b"shortcut")
                self.assertEqual(autostart.autostart_location(), str(shortcut))
                self.assertTrue(autostart.is_autostart_enabled())
                remove_legacy.assert_called_once_with()

                process_command = run.call_args.args[0]
                self.assertEqual(process_command[0], str(powershell))
                self.assertIn("Hidden", process_command)
                environment = run.call_args.kwargs["env"]
                self.assertEqual(environment["PAYPAMIN_FLOW_TARGET"], str(pythonw))
                self.assertIn("paypamin_flow_launcher.py", environment["PAYPAMIN_FLOW_ARGUMENTS"])
                self.assertNotIn(".pyw", environment["PAYPAMIN_FLOW_ARGUMENTS"])
                self.assertIn(MINIMIZED_START_ARG, environment["PAYPAMIN_FLOW_ARGUMENTS"])
                self.assertEqual(environment["PAYPAMIN_FLOW_ICON"], f"{icon},0")
                self.assertEqual(environment["PAYPAMIN_FLOW_WORKDIR"], str(source))
                self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000000)

                autostart.set_autostart(False)
                self.assertFalse(shortcut.exists())
                self.assertFalse(autostart.is_autostart_enabled())
                self.assertEqual(remove_legacy.call_count, 2)

    def test_failed_windows_shortcut_build_preserves_existing_shortcut(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source"
            source.mkdir()
            resource = temp / "resource"
            icon = resource / "assets" / "paypamin_flow.ico"
            icon.parent.mkdir(parents=True)
            icon.write_bytes(b"icon")
            powershell = temp / "Windows" / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
            powershell.parent.mkdir(parents=True)
            powershell.write_bytes(b"")
            shortcut = temp / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{APP_NAME}.lnk"
            shortcut.parent.mkdir(parents=True)
            shortcut.write_bytes(b"known-good")

            def fail_shortcut(process_command, **kwargs):
                Path(kwargs["env"]["PAYPAMIN_FLOW_SHORTCUT"]).write_bytes(b"incomplete")
                return SimpleNamespace(returncode=1)

            with mock.patch.dict(os.environ, {"APPDATA": str(temp / "Roaming"), "SystemRoot": str(temp / "Windows")}), \
                    mock.patch.object(autostart, "SOURCE_DIR", source), \
                    mock.patch.object(autostart, "RESOURCE_DIR", resource), \
                    mock.patch.object(autostart.subprocess, "run", side_effect=fail_shortcut):
                with self.assertRaises(autostart.AutostartError):
                    autostart._create_windows_shortcut(
                        shortcut,
                        ["pythonw.exe", str(source / "paypamin_flow_launcher.py"), MINIMIZED_START_ARG],
                    )
            self.assertEqual(shortcut.read_bytes(), b"known-good")
            self.assertFalse(shortcut.with_name(f"{shortcut.stem}.tmp.lnk").exists())

    def test_legacy_windows_run_value_is_removed(self):
        fake_winreg = mock.MagicMock()
        fake_winreg.HKEY_CURRENT_USER = "HKCU"
        fake_winreg.KEY_SET_VALUE = 2
        key_context = mock.MagicMock()
        key_context.__enter__.return_value = key_context
        fake_winreg.OpenKey.return_value = key_context
        with mock.patch.dict(sys.modules, {"winreg": fake_winreg}):
            autostart._remove_legacy_windows_run_value()
        fake_winreg.DeleteValue.assert_called_once_with(key_context, autostart.WINDOWS_VALUE_NAME)

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
                self.assertTrue(payload["ProgramArguments"][1].endswith("paypamin_flow_launcher.py"))
                self.assertFalse(payload["ProgramArguments"][1].endswith(".pyw"))
                self.assertEqual(payload["ProgramArguments"][2], MINIMIZED_START_ARG)
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
