import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DECLINED_MARKER = "python-offer.declined"


class WindowsPythonRuntimeLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.launcher = (ROOT / "start_paypamin_flow.vbs").read_text(encoding="utf-8")

    def test_inventory_precedes_missing_runtime_installation(self):
        path_check = self.launcher.index('pythonwPath = FindOnPath("pythonw.exe")')
        known_check = self.launcher.index("knownPythonPath = FindKnownPython()")
        install = self.launcher.index('" install default"')
        self.assertLess(path_check, known_check)
        self.assertLess(known_check, install)

    def test_new_runtime_is_installed_only_in_the_missing_python_branch(self):
        missing_branch = self.launcher.index('WriteRuntimeLog "No existing Python runtime found.')
        before_missing_branch = self.launcher[:missing_branch]
        after_missing_branch = self.launcher[missing_branch:]
        self.assertNotIn('" install default"', before_missing_branch)
        self.assertIn('" install default"', after_missing_branch)
        self.assertEqual(self.launcher.count('" install default"'), 1)
        self.assertIn("If Not hasPython Then\n" + '  WriteRuntimeLog "No existing Python runtime found.', self.launcher)

    def test_existing_runtime_is_never_updated_at_startup(self):
        self.assertNotIn("install --update", self.launcher)
        self.assertNotIn("runtimeMaintenanceDue", self.launcher)
        self.assertNotIn("MarkPythonRuntimeMaintenance", self.launcher)
        self.assertNotIn("python-runtime-week.txt", self.launcher)
        self.assertNotIn("Python kunde inte uppdateras", self.launcher)
        self.assertIn("An existing Python runtime is always reused unchanged", self.launcher)
        self.assertNotIn(" --force", self.launcher)
        self.assertNotIn(" --target", self.launcher)

    def test_failed_inventory_cannot_authorize_a_new_installation(self):
        guard = 'If Not hasPython And managerPath <> "" And Not managerInventoryOK Then'
        self.assertIn(guard, self.launcher)
        self.assertIn("Det gick inte att kontrollera Python-installationen. Ingen ny Python har installerats.", self.launcher)
        self.assertIn("If anyCode <> 0 Then", self.launcher)
        self.assertIn("managerInventoryOK = False", self.launcher)
        failure_handler = self.launcher.split("Sub FailRuntime(message)", 1)[1]
        self.assertIn("WScript.Quit 1", failure_handler)

    def test_store_aliases_cannot_trigger_an_implicit_python_install(self):
        self.assertIn('FindOnPath("pythonw.exe")', self.launcher)
        self.assertIn('FindOnPath("python.exe")', self.launcher)
        self.assertIn("IsWindowsAppsPath(candidate)", self.launcher)
        self.assertIn("If Not pythonAlias Then", self.launcher)

    def test_unmanaged_python_is_reused_without_replacement(self):
        self.assertIn("An existing Python runtime is always reused unchanged", self.launcher)
        self.assertIn("Starting PayPamin Flow with existing Python: ", self.launcher)
        self.assertNotRegex(self.launcher, r"(?i)\b(uninstall|remove-python|python\.org/downloads/\d)")

    def test_windows_launcher_does_not_upgrade_addons(self):
        self.assertNotIn("addonsMaintenanceDue", self.launcher)
        self.assertNotIn("PythonAddonsMaintenanceDue", self.launcher)
        self.assertNotIn("MarkPythonAddonsMaintenance", self.launcher)
        self.assertNotIn("python-addons-week.txt", self.launcher)
        self.assertNotIn("-m pip install --upgrade", self.launcher)
        self.assertIn("Add-on upgrades are offered manually inside the app.", self.launcher)
        self.assertNotIn(" -m venv", self.launcher)

    def test_app_exposes_addons_as_a_manual_help_offer(self):
        source = (ROOT / "paypamin_flow.py").read_text(encoding="utf-8")
        self.assertIn("help_menu.add_command(label=_('Uppdatera Python-tillägg'),command=self.update_python_addons)", source)
        self.assertIn("confirmed=messagebox.askyesno(", source)
        self.assertNotIn("_run_scheduled_python_addon_maintenance", source)

    def test_all_helper_commands_are_hidden_and_arguments_are_preserved(self):
        self.assertIn("sh.Run cmd, 0, False", self.launcher)
        self.assertIn(", 0, True)", self.launcher)
        self.assertIn("For Each argument In WScript.Arguments", self.launcher)
        self.assertIn("Quote(CStr(argument))", self.launcher)
        self.assertIn("paypamin_flow_launcher.py", self.launcher)

    def test_windows_manager_package_id_is_official_and_not_a_python_version(self):
        self.assertIn("install 9NQ7512CXL7T -e", self.launcher)
        self.assertIn("--accept-package-agreements --disable-interactivity", self.launcher)
        self.assertNotRegex(self.launcher, r"install\s+(?:3|python)\.\d")

    def test_unix_launcher_does_not_modify_system_python(self):
        launcher = (ROOT / "start_paypamin_flow.sh").read_text(encoding="utf-8")
        self.assertIn('command -v "$name"', launcher)
        self.assertNotRegex(launcher, r"(?i)\b(apt|apt-get|brew|pymanager|winget|pip)\b.*\b(install|upgrade|update)\b")
        self.assertNotIn("sudo", launcher)


class StartFileContractTests(unittest.TestCase):
    """One start file per platform, offering Python only when it is missing."""

    def text(self, name):
        return (ROOT / name).read_text(encoding="utf-8")

    def test_every_platform_has_exactly_one_start_file(self):
        for name in ("start_paypamin_flow.vbs", "start_paypamin_flow.sh", "start_paypamin_flow.command"):
            self.assertTrue((ROOT / name).is_file(), name)
        for name in ("start_paypamin_flow.sh", "start_paypamin_flow.command"):
            self.assertTrue(os.access(ROOT / name, os.X_OK), name)
        # No separate installer script exists, and no .bat is shipped anywhere.
        self.assertFalse((ROOT / "Installera senaste Python.bat").exists())
        self.assertEqual(list(ROOT.glob("*.bat")), [])

    def test_a_present_runtime_never_triggers_a_question(self):
        windows = self.text("start_paypamin_flow.vbs")
        missing_branch = windows.index('WriteRuntimeLog "No existing Python runtime found.')
        prompt = windows.index("consent = MsgBox(")
        self.assertLess(missing_branch, prompt)
        self.assertLess(prompt, windows.index('If managerPath = "" Then'))
        self.assertEqual(windows.count("consent = MsgBox("), 1)
        for name in ("start_paypamin_flow.sh", "start_paypamin_flow.command"):
            script = self.text(name)
            self.assertIn("if PYTHON=$(find_python); then", script)
            self.assertLess(script.index("find_python()"), script.index("offer_install()"))
            # The app is launched before the offer can ever be reached.
            self.assertLess(script.index("paypamin_flow_launcher.py"), script.index("offer_install \"$NEED_SV"))

    def test_a_declined_offer_is_remembered_and_not_repeated(self):
        for name, marker_check in (
            ("start_paypamin_flow.vbs", "If fso.FileExists(DeclinedMarkerPath()) Then"),
            ("start_paypamin_flow.sh", 'if [ -f "$MARKER" ]; then'),
            ("start_paypamin_flow.command", 'if [ -f "$MARKER" ]; then'),
        ):
            script = self.text(name)
            self.assertIn(DECLINED_MARKER, script)
            self.assertIn(marker_check, script)
            self.assertIn(".paminnelseapp", script)

    def test_the_declined_marker_lives_in_the_application_folder(self):
        for name in ("start_paypamin_flow.vbs", "start_paypamin_flow.sh", "start_paypamin_flow.command"):
            script = self.text(name)
            marker_line = [line for line in script.splitlines() if DECLINED_MARKER in line][0]
            self.assertIn(".paminnelseapp", marker_line)

    def test_cancelling_the_windows_offer_is_not_a_refusal(self):
        windows = self.text("start_paypamin_flow.vbs")
        self.assertIn("vbYesNoCancel", windows)
        self.assertIn("If consent = vbCancel Then", windows)
        cancel_branch = windows.split("If consent = vbCancel Then", 1)[1].split("If consent <> vbYes Then", 1)[0]
        self.assertNotIn("CreateTextFile", cancel_branch)
        self.assertNotIn("DeclinedMarkerPath(), True", cancel_branch)

    def test_installing_python_requires_an_accepted_offer_on_windows(self):
        windows = self.text("start_paypamin_flow.vbs")
        accepted = windows.index("If consent <> vbYes Then")
        install = windows.index('" install default"')
        self.assertLess(accepted, install)
        self.assertIn('WriteRuntimeLog "The Python installation offer was accepted by the user."', windows)

    def test_unix_start_files_only_link_to_the_official_installer(self):
        for name, url in (
            ("start_paypamin_flow.sh", "https://www.python.org/downloads/"),
            ("start_paypamin_flow.command", "https://www.python.org/downloads/macos/"),
        ):
            script = self.text(name)
            self.assertIn(url, script)
            self.assertNotIn("sudo", script)

    def test_unix_start_files_require_3_10_and_tkinter(self):
        for name in ("start_paypamin_flow.sh", "start_paypamin_flow.command"):
            script = self.text(name)
            self.assertIn("sys.version_info >= (3, 10)", script)
            self.assertIn("runtime_has_tkinter", script)
            self.assertIn("paypamin_flow_launcher.py", script)
            self.assertIn('"$@"', script)

    def test_macos_start_file_closes_its_own_terminal_window(self):
        script = self.text("start_paypamin_flow.command")
        self.assertIn("close_own_terminal_window", script)
        self.assertIn("start_paypamin_flow.command\" then close w", script)
        self.assertIn('nohup "$PYTHON"', script)

    def test_the_macos_stub_is_not_started_without_command_line_tools(self):
        script = self.text("start_paypamin_flow.command")
        self.assertIn("xcode-select -p", script)
        self.assertIn("apple_stub_without_tools", script)

    def test_no_start_file_contains_a_python_upgrade(self):
        for name in ("start_paypamin_flow.vbs", "start_paypamin_flow.sh", "start_paypamin_flow.command"):
            script = self.text(name)
            self.assertNotIn("install --update", script)
            self.assertNotIn("pip install --upgrade", script)
            self.assertNotIn(" -m venv", script)


class StartFilePackagingTests(unittest.TestCase):
    def test_all_three_start_files_ship_in_the_release(self):
        import app_info

        for name in ("start_paypamin_flow.vbs", "start_paypamin_flow.sh", "start_paypamin_flow.command"):
            self.assertIn(name, app_info.PYTHON_PACKAGE_REQUIRED_FILES)
            self.assertTrue(app_info.is_python_package_file(name), name)

    def test_a_windows_batch_installer_can_never_be_shipped(self):
        import app_info

        for name in ("Installera senaste Python.bat", "python.bat", "install_python.cmd"):
            self.assertFalse(app_info.is_python_package_file(name), name)


@unittest.skipUnless(os.name == "posix" and shutil.which("sh"), "POSIX shell required")
class ShellStartFileBehaviourTests(unittest.TestCase):
    """Run the real Linux start file against a fake Python, without a GUI."""

    def setUp(self):
        self.sh = shutil.which("sh")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.bin = self.root / "bin"
        self.app = self.root / "app"
        for folder in (self.home, self.bin, self.app):
            folder.mkdir()
        for tool in ("dirname", "mkdir", "date"):
            found = shutil.which(tool)
            if found:
                (self.bin / tool).symlink_to(found)
        launcher = self.app / "start_paypamin_flow.sh"
        shutil.copy2(ROOT / "start_paypamin_flow.sh", launcher)
        # Point the hard-coded fallbacks somewhere that cannot exist, so only
        # the PATH lookup decides in this test.
        launcher.write_text(
            launcher.read_text(encoding="utf-8").replace(
                "/usr/local/bin/python3 /opt/homebrew/bin/python3 /usr/bin/python3",
                str(self.root / "missing" / "python3"),
            ),
            encoding="utf-8",
        )
        launcher.chmod(0o755)
        self.marker = self.home / ".paminnelseapp" / DECLINED_MARKER

    def fake_python(self, *, tkinter=True, version="3.11.9"):
        script = self.bin / "python3"
        tkinter_exit = 0 if tkinter else 1
        script.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "-c" ]; then\n'
            f'  case "$2" in *tkinter*) exit {tkinter_exit} ;; esac\n'
            f'  case "$2" in *platform*) printf \'%s\\n\' "{version}" ;; esac\n'
            "  exit 0\n"
            "fi\n"
            'printf "%s\\n" "LAUNCHED $*"\n',
            encoding="utf-8",
        )
        script.chmod(0o755)

    def too_old_python(self):
        script = self.bin / "python3"
        script.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "-c" ]; then\n'
            '  case "$2" in *3, 10*) exit 2 ;; esac\n'
            "  exit 0\n"
            "fi\n"
            'printf "%s\\n" "LAUNCHED $*"\n',
            encoding="utf-8",
        )
        script.chmod(0o755)

    def run_start_file(self, *args):
        return subprocess.run(
            [self.sh, str(self.app / "start_paypamin_flow.sh"), *args],
            capture_output=True,
            text=True,
            env={"HOME": str(self.home), "PATH": str(self.bin)},
            check=False,
        )

    def test_existing_python_starts_the_app_without_any_question(self):
        self.fake_python()
        result = self.run_start_file("--minimized")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LAUNCHED", result.stdout)
        self.assertIn("--minimized", result.stdout)
        self.assertNotIn("python.org", result.stderr + result.stdout)
        self.assertFalse(self.marker.exists())

    def test_missing_python_offers_once_and_starts_nothing(self):
        result = self.run_start_file()
        self.assertEqual(result.returncode, 1)
        self.assertIn("https://www.python.org/downloads/", result.stderr)
        self.assertNotIn("LAUNCHED", result.stdout)
        self.assertTrue(self.marker.is_file())

    def test_a_remembered_refusal_is_not_offered_again(self):
        self.marker.parent.mkdir(parents=True)
        self.marker.write_text("declined 2026-01-01 00:00:00\n", encoding="utf-8")
        result = self.run_start_file()
        self.assertEqual(result.returncode, 1)
        self.assertIn("ställs inte om", result.stderr)
        self.assertIn("not repeated", result.stderr)

    def test_python_without_tkinter_is_named_instead_of_reinstalled(self):
        self.fake_python(tkinter=False)
        result = self.run_start_file()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Tkinter", result.stderr)
        self.assertIn("3.11.9", result.stderr)
        self.assertFalse(self.marker.exists())

    def test_a_python_older_than_3_10_is_not_treated_as_usable(self):
        self.too_old_python()
        result = self.run_start_file()
        self.assertNotIn("LAUNCHED", result.stdout)
        self.assertIn("https://www.python.org/downloads/", result.stderr)

    def test_a_marker_never_blocks_a_working_python(self):
        self.marker.parent.mkdir(parents=True)
        self.marker.write_text("declined\n", encoding="utf-8")
        self.fake_python()
        result = self.run_start_file()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LAUNCHED", result.stdout)


if __name__ == "__main__":
    unittest.main()
