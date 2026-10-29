import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote

import mail_compose


class ThunderbirdDetectionTests(unittest.TestCase):
    def test_non_windows_never_reads_registry(self):
        with patch.object(mail_compose.sys, "platform", "linux"):
            with patch.object(mail_compose, "_registry_value") as read:
                self.assertFalse(mail_compose.windows_uses_thunderbird())
            read.assert_not_called()
            self.assertEqual(mail_compose._registry_value("HKCU", "unused"), "")

    def test_windows_11_user_choice_thunderbird_is_preferred(self):
        values = {
            ("HKCU", mail_compose.USERCHOICE_MAILTO_KEY, "ProgId"): "Thunderbird.Url.mailto",
            ("HKCU", mail_compose.REGISTERED_MAIL_CLIENT_KEY, ""): "Microsoft Outlook",
        }
        with patch.object(mail_compose.sys, "platform", "win32"):
            with patch.object(mail_compose, "_registry_value", side_effect=lambda *args: values.get(args, "")) as read:
                self.assertTrue(mail_compose.windows_uses_thunderbird())
        read.assert_called_once_with("HKCU", mail_compose.USERCHOICE_MAILTO_KEY, "ProgId")

    def test_other_windows_11_user_choice_overrides_legacy_thunderbird_value(self):
        values = {
            ("HKCU", mail_compose.USERCHOICE_MAILTO_KEY, "ProgId"): "Outlook.URL.mailto.15",
            ("HKCU", mail_compose.REGISTERED_MAIL_CLIENT_KEY, ""): "Mozilla Thunderbird",
        }
        with patch.object(mail_compose.sys, "platform", "win32"):
            with patch.object(mail_compose, "_registry_value", side_effect=lambda *args: values.get(args, "")) as read:
                self.assertFalse(mail_compose.windows_uses_thunderbird())
        read.assert_called_once_with("HKCU", mail_compose.USERCHOICE_MAILTO_KEY, "ProgId")

    def test_registered_mail_client_is_fallback_when_user_choice_is_missing(self):
        values = {
            ("HKCU", mail_compose.USERCHOICE_MAILTO_KEY, "ProgId"): "",
            ("HKCU", mail_compose.REGISTERED_MAIL_CLIENT_KEY, ""): "Mozilla Thunderbird",
        }
        with patch.object(mail_compose.sys, "platform", "win32"):
            with patch.object(mail_compose, "_registry_value", side_effect=lambda root, path, name="": values.get((root, path, name), "")):
                self.assertTrue(mail_compose.windows_uses_thunderbird())

    def test_system_default_is_fallback_when_user_values_are_missing(self):
        values = {
            ("HKCU", mail_compose.USERCHOICE_MAILTO_KEY, "ProgId"): "",
            ("HKCU", mail_compose.REGISTERED_MAIL_CLIENT_KEY, ""): "",
            ("HKLM", mail_compose.REGISTERED_MAIL_CLIENT_KEY, ""): "Mozilla Thunderbird",
        }
        with patch.object(mail_compose.sys, "platform", "win32"):
            with patch.object(mail_compose, "_registry_value", side_effect=lambda root, path, name="": values.get((root, path, name), "")):
                self.assertTrue(mail_compose.windows_uses_thunderbird())

    def test_executable_lookup_uses_registered_app_path(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            executable = Path(temporary_directory) / "thunderbird.exe"
            executable.write_bytes(b"test")
            with patch.object(mail_compose.sys, "platform", "win32"):
                with patch.object(mail_compose, "_registry_value", return_value=str(executable)):
                    with patch.object(mail_compose.shutil, "which") as which:
                        self.assertEqual(mail_compose._find_thunderbird_executable(), str(executable))
            which.assert_not_called()

    def test_registered_command_supports_quotes_spaces_and_unc_paths(self):
        cases = (
            (r'"C:\Program Files\Mozilla Thunderbird\thunderbird.exe" -mail', r'C:\Program Files\Mozilla Thunderbird\thunderbird.exe'),
            (r'C:\Thunderbird Test\thunderbird.exe -mail', r'C:\Thunderbird Test\thunderbird.exe'),
            (r'"\\server\share\Mozilla Thunderbird\thunderbird.exe" -mail', r'\\server\share\Mozilla Thunderbird\thunderbird.exe'),
        )
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(mail_compose._executable_from_command(command), expected)

    def test_default_executable_is_not_looked_up_for_another_mailer(self):
        with patch.object(mail_compose, "windows_uses_thunderbird", return_value=False):
            with patch.object(mail_compose, "_find_thunderbird_executable") as find:
                self.assertIsNone(mail_compose.default_thunderbird_executable())
        find.assert_not_called()


class ThunderbirdComposeTests(unittest.TestCase):
    def content(self):
        return {
            "recipients": ["first@example.com", "second@example.com"],
            "bcc": "rl@tadega.com",
            "subject": "SV: Faktura 1001, kundens ärende",
            "body": "Hej!\n\nKundens text, med 'citat' och åäö.\nBifogad P2.",
        }

    def test_compose_uses_native_path_for_regular_reminder_filename(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            pdf = Path(temporary_directory) / "paminnelse(2)_6258.pdf"
            pdf.write_bytes(b"pdf")
            compose = mail_compose.build_thunderbird_compose(self.content(), pdf)
            fields = dict(part.split("=", 1) for part in compose.split(","))

        attachment = unquote(fields["attachment"])
        self.assertEqual(attachment, str(pdf.resolve()))
        self.assertFalse(attachment.startswith("file:"))

    def test_compose_percent_encodes_fields_and_pdf_uri(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            pdf = Path(temporary_directory) / "Påminnelse 2, kundens 'kopia'.pdf"
            pdf.write_bytes(b"pdf")
            compose = mail_compose.build_thunderbird_compose(self.content(), pdf)
            fields = dict(part.split("=", 1) for part in compose.split(","))

        self.assertEqual(set(fields), {"to", "bcc", "subject", "body", "attachment", "format"})
        self.assertEqual(unquote(fields["to"]), "first@example.com,second@example.com")
        self.assertEqual(unquote(fields["bcc"]), "rl@tadega.com")
        self.assertEqual(unquote(fields["subject"]), self.content()["subject"])
        self.assertEqual(unquote(fields["body"]), self.content()["body"])
        self.assertEqual(unquote(fields["attachment"]), pdf.resolve().as_uri())
        self.assertEqual(fields["format"], "text")
        self.assertEqual(compose.count(","), 5)
        self.assertNotIn("\n", compose)
        self.assertNotIn("å", compose)

    def test_open_draft_uses_argument_list_no_shell_and_no_console(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            pdf = Path(temporary_directory) / "reminder.pdf"
            pdf.write_bytes(b"pdf")
            executable = r"C:\Program Files\Mozilla Thunderbird\thunderbird.exe"
            with patch.object(mail_compose.sys, "platform", "win32"):
                with patch.object(mail_compose.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
                    with patch.object(mail_compose.subprocess, "Popen") as popen:
                        popen.return_value.poll.return_value = None
                        opened = mail_compose.open_thunderbird_draft(executable, self.content(), pdf)

        self.assertTrue(opened)
        command = popen.call_args.args[0]
        self.assertEqual(command[:2], [executable, "-compose"])
        self.assertIn("attachment=", command[2])
        self.assertNotIn("shell", popen.call_args.kwargs)
        self.assertEqual(popen.call_args.kwargs["stdin"], mail_compose.subprocess.DEVNULL)
        self.assertEqual(popen.call_args.kwargs["stdout"], mail_compose.subprocess.DEVNULL)
        self.assertEqual(popen.call_args.kwargs["stderr"], mail_compose.subprocess.DEVNULL)
        self.assertEqual(popen.call_args.kwargs["creationflags"], 0x08000000)

    def test_missing_pdf_never_starts_thunderbird(self):
        with patch.object(mail_compose.subprocess, "Popen") as popen:
            with self.assertRaises(FileNotFoundError):
                mail_compose.open_thunderbird_draft(
                    "thunderbird.exe", self.content(), Path("/definitely/missing/reminder.pdf")
                )
        popen.assert_not_called()

    def test_empty_pdf_never_starts_thunderbird(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            pdf = Path(temporary_directory) / "empty.pdf"
            pdf.write_bytes(b"")
            with patch.object(mail_compose.subprocess, "Popen") as popen:
                with self.assertRaises(ValueError):
                    mail_compose.open_thunderbird_draft("thunderbird.exe", self.content(), pdf)
        popen.assert_not_called()

    def test_immediate_thunderbird_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            pdf = Path(temporary_directory) / "reminder.pdf"
            pdf.write_bytes(b"pdf")
            with patch.object(mail_compose.subprocess, "Popen") as popen:
                popen.return_value.poll.return_value = 2
                with self.assertRaisesRegex(RuntimeError, "code 2"):
                    mail_compose.open_thunderbird_draft("thunderbird.exe", self.content(), pdf)


if __name__ == "__main__":
    unittest.main()
