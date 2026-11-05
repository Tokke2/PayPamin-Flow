import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WindowsPythonRuntimeLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.launcher = (ROOT / "start_paypamin_flow.vbs").read_text(encoding="utf-8")

    def test_inventory_precedes_every_runtime_change(self):
        path_check = self.launcher.index('pythonwPath = FindOnPath("pythonw.exe")')
        known_check = self.launcher.index("knownPythonPath = FindKnownPython()")
        update = self.launcher.index('" install --update --by-id "')
        install = self.launcher.index('" install default"')
        self.assertLess(path_check, known_check)
        self.assertLess(known_check, update)
        self.assertLess(known_check, install)

    def test_new_runtime_is_installed_only_in_the_missing_python_branch(self):
        missing_branch = self.launcher.index('WriteRuntimeLog "No existing Python runtime found.')
        before_missing_branch = self.launcher[:missing_branch]
        after_missing_branch = self.launcher[missing_branch:]
        self.assertNotIn('" install default"', before_missing_branch)
        self.assertIn('" install default"', after_missing_branch)
        self.assertEqual(self.launcher.count('" install default"'), 1)
        self.assertIn("If Not hasPython Then\n" + '  WriteRuntimeLog "No existing Python runtime found.', self.launcher)

    def test_existing_runtime_update_is_exactly_scoped_to_its_install_id(self):
        self.assertIn('" install --update --by-id " & Quote(managedId)', self.launcher)
        self.assertIn("If canUpdateManaged Then", self.launcher)
        self.assertIn("pythonwPath = managedLauncherPath", self.launcher)
        self.assertIn("IsSafeInstallId(managedId)", self.launcher)
        self.assertIn('"--only-managed "', self.launcher)
        self.assertNotRegex(self.launcher, r"install\s+--update\s*(?:\"|'|$)")
        self.assertNotIn(" --force", self.launcher)
        self.assertNotIn(" --target", self.launcher)

    def test_failed_inventory_cannot_authorize_a_new_installation(self):
        guard = 'If Not hasPython And managerPath <> "" And Not managerInventoryOK Then'
        self.assertIn(guard, self.launcher)
        self.assertIn("Det gick inte att kontrollera Python-installationen. Ingen ny Python har installerats.", self.launcher)
        self.assertIn("If managedCode <> 0 Then\n    managerInventoryOK = False", self.launcher)
        failure_handler = self.launcher.split("Sub FailRuntime(message)", 1)[1]
        self.assertIn("WScript.Quit 1", failure_handler)

    def test_store_aliases_cannot_trigger_an_implicit_python_install(self):
        self.assertIn('FindOnPath("pythonw.exe")', self.launcher)
        self.assertIn('FindOnPath("python.exe")', self.launcher)
        self.assertIn("IsWindowsAppsPath(candidate)", self.launcher)
        self.assertIn("If Not pythonAlias Then", self.launcher)

    def test_unmanaged_python_is_reused_without_replacement(self):
        self.assertIn("Existing Python is not confirmed as the selected manager-managed runtime.", self.launcher)
        self.assertIn("Leaving it unchanged; no update or new installation was requested.", self.launcher)
        self.assertNotRegex(self.launcher, r"(?i)\b(uninstall|remove-python|python\.org/downloads/\d)")

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
