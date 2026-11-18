import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import console_free
from test_database import load_headless_app


class ConsoleFreeSubprocessTests(unittest.TestCase):
    def tearDown(self):
        console_free._installed = False

    def test_windows_children_preserve_flags_and_add_no_window(self):
        calls = []
        original_popen = console_free.subprocess.Popen
        original_flag = getattr(console_free.subprocess, "CREATE_NO_WINDOW", None)

        def fake_popen(*args, **kwargs):
            calls.append((args, kwargs))
            return object()

        try:
            console_free.subprocess.Popen = fake_popen
            console_free.subprocess.CREATE_NO_WINDOW = 0x08000000
            console_free._installed = False
            with patch.object(console_free.sys, "platform", "win32"):
                console_free.configure_console_free_subprocesses()
                wrapped_popen = console_free.subprocess.Popen
                console_free.configure_console_free_subprocesses()
                self.assertIs(console_free.subprocess.Popen, wrapped_popen)
                console_free.subprocess.Popen("ocr-tool", creationflags=0x08)
                console_free.subprocess.Popen("other-tool")
        finally:
            console_free.subprocess.Popen = original_popen
            if original_flag is None:
                del console_free.subprocess.CREATE_NO_WINDOW
            else:
                console_free.subprocess.CREATE_NO_WINDOW = original_flag
        self.assertEqual(calls[0][1]["creationflags"], 0x08000008)
        self.assertEqual(calls[1][1]["creationflags"], 0x08000000)

    def test_non_windows_does_not_patch_popen(self):
        with patch.object(console_free.sys, "platform", "linux"), patch.object(
            console_free.subprocess, "Popen"
        ) as popen:
            console_free.configure_console_free_subprocesses()
            self.assertIs(console_free.subprocess.Popen, popen)
        self.assertFalse(console_free._installed)


    def test_a_scan_tool_started_through_run_gets_no_window(self):
        """pdf2image and pytesseract reach Popen through subprocess.run too."""
        calls = []

        class FakeProcess:
            returncode = 0

            def __init__(self, args):
                self.args = args

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def communicate(self, *_args, **_kwargs):
                return b"", b""

            def poll(self):
                return 0

        def fake_popen(*args, **kwargs):
            calls.append((args, kwargs))
            return FakeProcess(args[0] if args else kwargs.get("args"))

        original_popen = console_free.subprocess.Popen
        original_flag = getattr(console_free.subprocess, "CREATE_NO_WINDOW", None)
        try:
            console_free.subprocess.Popen = fake_popen
            console_free.subprocess.CREATE_NO_WINDOW = 0x08000000
            console_free._installed = False
            with patch.object(console_free.sys, "platform", "win32"):
                console_free.configure_console_free_subprocesses()
                console_free.subprocess.run(["pdftoppm", "-v"], capture_output=True, check=False)
        finally:
            console_free.subprocess.Popen = original_popen
            if original_flag is None:
                del console_free.subprocess.CREATE_NO_WINDOW
            else:
                console_free.subprocess.CREATE_NO_WINDOW = original_flag
            console_free._installed = False
        self.assertEqual(calls[0][1]["creationflags"] & 0x08000000, 0x08000000)



class ConsoleWindowTests(unittest.TestCase):
    """The three safeguards against a terminal window on Windows."""

    def test_nothing_is_hidden_on_other_platforms(self):
        for platform in ("linux", "darwin"):
            with self.subTest(platform=platform), patch.object(console_free.sys, "platform", platform):
                self.assertFalse(console_free.hide_own_console_window())
                self.assertIsNone(console_free.console_free_python(__import__("sys").executable))
                self.assertIsNone(console_free.relaunch_console_free("app.pyw"))

    def fake_ctypes(self, handle, attached=1):
        class FakeFunction:
            def __init__(self, result):
                self.result = result
                self.calls = []

            def __call__(self, *args):
                self.calls.append(args)
                return self.result

        self.get_console = FakeFunction(handle)
        self.show_window = FakeFunction(1)
        self.get_processes = FakeFunction(attached)
        kernel32 = SimpleNamespace(
            GetConsoleWindow=self.get_console,
            GetConsoleProcessList=self.get_processes,
        )
        user32 = SimpleNamespace(ShowWindow=self.show_window)

        class FakeArray:
            def __mul__(self, count):
                return lambda: [0] * count

        return SimpleNamespace(
            windll=SimpleNamespace(kernel32=kernel32, user32=user32),
            c_uint32=FakeArray(),
        )

    def test_the_console_of_this_process_is_hidden(self):
        fake = self.fake_ctypes(1234, attached=1)
        with patch.object(console_free.sys, "platform", "win32"), patch.dict(
            __import__("sys").modules, {"ctypes": fake}
        ):
            self.assertTrue(console_free.hide_own_console_window())
        self.assertEqual(self.show_window.calls, [(1234, 0)])

    def test_a_terminal_the_user_opened_is_left_alone(self):
        """cmd.exe + python.exe share one console; that window is not ours."""
        fake = self.fake_ctypes(1234, attached=3)
        with patch.object(console_free.sys, "platform", "win32"), patch.dict(
            __import__("sys").modules, {"ctypes": fake}
        ):
            self.assertFalse(console_free.hide_own_console_window())
        self.assertEqual(self.show_window.calls, [])

    def test_a_start_without_a_console_handle_is_not_an_error(self):
        fake = self.fake_ctypes(0)
        with patch.object(console_free.sys, "platform", "win32"), patch.dict(
            __import__("sys").modules, {"ctypes": fake}
        ):
            self.assertFalse(console_free.hide_own_console_window())
        self.assertEqual(self.show_window.calls, [])

    def test_a_failing_windows_call_never_raises(self):
        class Broken:
            def __getattr__(self, name):
                raise OSError("ctypes unavailable")

        fake_ctypes = SimpleNamespace(windll=Broken())
        with patch.object(console_free.sys, "platform", "win32"), patch.dict(
            __import__("sys").modules, {"ctypes": fake_ctypes}
        ):
            self.assertFalse(console_free.hide_own_console_window())

    def test_pythonw_is_found_beside_this_interpreter(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            python = folder / "python.exe"
            pythonw = folder / "pythonw.exe"
            python.write_text("", encoding="utf-8")
            with patch.object(console_free.sys, "platform", "win32"):
                self.assertIsNone(console_free.console_free_python(str(python)))
                pythonw.write_text("", encoding="utf-8")
                self.assertEqual(console_free.console_free_python(str(python)), pythonw)
                # A start that is already console-free is left alone.
                self.assertIsNone(console_free.console_free_python(str(pythonw)))

    def test_the_launcher_restarts_under_pythonw_once(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            python = folder / "python.exe"
            (folder / "pythonw.exe").write_text("", encoding="utf-8")
            started = []
            environment = {}
            with patch.object(console_free.sys, "platform", "win32"), patch.object(
                console_free.sys, "executable", str(python)
            ), patch.object(console_free, "subprocess") as subprocess_module, patch.dict(
                console_free.os.environ, environment, clear=True
            ):
                subprocess_module.Popen.side_effect = lambda command, **kwargs: started.append((command, kwargs))
                self.assertEqual(console_free.relaunch_console_free(folder / "start.pyw", ["--minimized"]), 0)
                command, kwargs = started[0]
                self.assertEqual(command, [str(folder / "pythonw.exe"), str(folder / "start.pyw"), "--minimized"])
                self.assertEqual(kwargs["env"][console_free.CONSOLE_FREE_GUARD], "1")
                # The relaunched copy is guarded, so it cannot bounce back.
                console_free.os.environ[console_free.CONSOLE_FREE_GUARD] = "1"
                self.assertIsNone(console_free.relaunch_console_free(folder / "start.pyw"))
                self.assertEqual(len(started), 1)

    def test_a_failed_restart_falls_back_to_hiding_the_console(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            python = folder / "python.exe"
            (folder / "pythonw.exe").write_text("", encoding="utf-8")
            with patch.object(console_free.sys, "platform", "win32"), patch.object(
                console_free.sys, "executable", str(python)
            ), patch.object(console_free, "subprocess") as subprocess_module, patch.dict(
                console_free.os.environ, {}, clear=True
            ):
                subprocess_module.Popen.side_effect = OSError("cannot start")
                self.assertIsNone(console_free.relaunch_console_free(folder / "start.pyw"))


class LauncherConsoleTests(unittest.TestCase):
    """The launcher is the first code that runs, so it is tested directly."""

    def setUp(self):
        import paypamin_flow_launcher

        self.launcher = paypamin_flow_launcher

    def test_a_relaunch_never_imports_the_app_twice(self):
        with patch.object(self.launcher.Path, "resolve", return_value=Path("/app/start.pyw")), patch(
            "console_free.relaunch_console_free", return_value=0
        ) as relaunch, patch("console_free.hide_own_console_window") as hide, patch.dict(
            "sys.modules", {"paypamin_flow": __import__("types").ModuleType("paypamin_flow")}
        ) as modules:
            modules["paypamin_flow"].main = lambda: (_ for _ in ()).throw(AssertionError("must not run"))
            self.assertEqual(self.launcher.run(), 0)
        relaunch.assert_called_once()
        hide.assert_not_called()

    def test_the_console_is_hidden_when_no_relaunch_happens(self):
        served = []
        fake_app = __import__("types").ModuleType("paypamin_flow")
        fake_app.main = lambda: served.append("main")
        with patch("console_free.relaunch_console_free", return_value=None), patch(
            "console_free.hide_own_console_window"
        ) as hide, patch.dict("sys.modules", {"paypamin_flow": fake_app}):
            self.assertEqual(self.launcher.run(), 0)
        hide.assert_called_once_with()
        self.assertEqual(served, ["main"])


class ApplicationStartupTests(unittest.TestCase):
    def test_main_configures_console_free_children_before_app_start(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = load_headless_app(Path(temporary_directory))
            events = []
            fake_window = SimpleNamespace(
                start_minimized=lambda: events.append("minimized"),
                mainloop=lambda: events.append("mainloop"),
            )
            try:
                with patch.object(
                    app, "configure_console_free_subprocesses", side_effect=lambda: events.append("console-free")
                ), patch.object(
                    app, "configure_windows_app_identity", side_effect=lambda: events.append("windows-identity")
                ), patch.object(app, "init_db", side_effect=lambda: events.append("database")), patch.object(
                    app, "ReminderApp", return_value=fake_window
                ):
                    app.main()
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()
            self.assertEqual(
                events, ["console-free", "windows-identity", "database", "minimized", "mainloop"]
            )

    def test_minimized_start_flag_hides_window_before_mainloop(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = load_headless_app(Path(temporary_directory))
            events = []
            fake_window = SimpleNamespace(
                start_minimized=lambda: events.append("minimized"),
                hide_to_tray=lambda: events.append("hidden"),
                mainloop=lambda: events.append("mainloop"),
            )
            try:
                with patch.object(
                    app, "configure_console_free_subprocesses", side_effect=lambda: events.append("console-free")
                ), patch.object(
                    app, "configure_windows_app_identity", side_effect=lambda: events.append("windows-identity")
                ), patch.object(app, "init_db", side_effect=lambda: events.append("database")), patch.object(
                    app, "ReminderApp", return_value=fake_window
                ), patch.object(app.sys, "argv", ["paypamin_flow_launcher.py", "--minimized"]):
                    app.main()
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()
            self.assertEqual(
                events, ["console-free", "windows-identity", "database", "minimized", "mainloop"]
            )

    def test_normal_start_is_minimized_without_any_flag_or_setting(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = load_headless_app(Path(temporary_directory))
            events = []
            fake_window = SimpleNamespace(
                start_minimized=lambda: events.append("minimized"),
                mainloop=lambda: events.append("mainloop"),
            )
            try:
                with patch.object(app, "configure_console_free_subprocesses"), patch.object(
                    app, "configure_windows_app_identity"
                ), patch.object(app, "init_db"), patch.object(
                    app, "ReminderApp", return_value=fake_window
                ), patch.object(app.sys, "argv", ["paypamin_flow.py"]):
                    app.main()
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()
            self.assertEqual(events, ["minimized", "mainloop"])

    def test_an_old_stored_preference_cannot_make_the_window_appear(self):
        """A settings row from an older version may say 0; it is ignored."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = load_headless_app(Path(temporary_directory))
            events = []
            fake_window = SimpleNamespace(
                start_minimized=lambda: events.append("minimized"),
                mainloop=lambda: events.append("mainloop"),
            )
            try:
                with patch.object(app, "configure_console_free_subprocesses"), patch.object(
                    app, "configure_windows_app_identity"
                ), patch.object(app, "init_db"), patch.object(
                    app, "ReminderApp", return_value=fake_window
                ), patch.object(
                    app, "setting", side_effect=lambda key: "0"
                ), patch.object(app.sys, "argv", ["paypamin_flow.py"]):
                    app.main()
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()
            self.assertEqual(events, ["minimized", "mainloop"])

    def test_the_console_is_hidden_before_anything_else_starts(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = load_headless_app(Path(temporary_directory))
            events = []
            fake_window = SimpleNamespace(
                start_minimized=lambda: events.append("minimized"),
                mainloop=lambda: events.append("mainloop"),
            )
            try:
                with patch.object(
                    app, "hide_own_console_window", side_effect=lambda: events.append("hide-console")
                ), patch.object(
                    app, "configure_console_free_subprocesses", side_effect=lambda: events.append("console-free")
                ), patch.object(
                    app, "configure_windows_app_identity", side_effect=lambda: events.append("windows-identity")
                ), patch.object(app, "init_db", side_effect=lambda: events.append("database")), patch.object(
                    app, "ReminderApp", return_value=fake_window
                ):
                    app.main()
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()
            self.assertEqual(
                events,
                ["hide-console", "console-free", "windows-identity", "database", "minimized", "mainloop"],
            )

    def test_unexpected_startup_errors_are_logged_and_reraised_for_the_gui_launcher(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = load_headless_app(Path(temporary_directory))
            try:
                with patch.object(app, "configure_console_free_subprocesses"), patch.object(
                    app, "configure_windows_app_identity"
                ), patch.object(app, "init_db", side_effect=RuntimeError("synthetic startup failure")):
                    with self.assertRaisesRegex(RuntimeError, "synthetic startup failure"):
                        app.main()
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()


if __name__ == "__main__":
    unittest.main()
