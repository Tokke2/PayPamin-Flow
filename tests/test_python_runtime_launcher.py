import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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
        self.assertIn("command -v python3", launcher)
        self.assertNotRegex(launcher, r"(?i)\b(apt|apt-get|brew|pymanager|winget|pip)\b.*\b(install|upgrade|update)\b")


if __name__ == "__main__":
    unittest.main()
