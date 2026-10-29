import os
import tempfile
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import patch

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


class ThunderbirdDraftTests(unittest.TestCase):
    def content(self):
        return {
            "recipients": ["first@example.com", "second@example.com"],
            "bcc": "rl@tadega.com",
            "subject": "SV: Faktura 1001, kundens ärende",
            "body": "Hej!\n\nKundens text, med 'citat' och åäö.\nBifogad P2.",
        }

    def parse_draft(self, draft_bytes):
        return BytesParser(policy=policy.default).parsebytes(draft_bytes)

    def test_draft_embeds_exact_pdf_and_preserves_all_fields(self):
        pdf_data = b"%PDF-1.7\nPayPamin test PDF\n%%EOF\n"
        with tempfile.TemporaryDirectory() as temporary_directory:
            pdf = Path(temporary_directory) / "Påminnelse 2, kundens 'kopia'.pdf"
            pdf.write_bytes(pdf_data)
            message = self.parse_draft(
                mail_compose.build_thunderbird_draft(self.content(), pdf)
            )

        self.assertEqual(message["X-Unsent"], "1")
        self.assertEqual(message["To"], "first@example.com, second@example.com")
        self.assertEqual(message["Bcc"], "rl@tadega.com")
        self.assertEqual(message["Subject"], self.content()["subject"])
        self.assertEqual(message.get_content_type(), "multipart/mixed")
        body = message.get_body(preferencelist=("plain",))
        self.assertIsNotNone(body)
        self.assertEqual(
            body.get_content().replace("\r\n", "\n").rstrip("\n"),
            self.content()["body"],
        )
        attachments = list(message.iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_content_type(), "application/pdf")
        self.assertEqual(attachments[0].get_filename(), pdf.name)
        self.assertEqual(attachments[0].get_payload(decode=True), pdf_data)

    def test_write_draft_creates_closed_parseable_eml_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            pdf = Path(temporary_directory) / "paminnelse(2)_6258.pdf"
            pdf.write_bytes(b"pdf")
            draft_path = mail_compose.write_thunderbird_draft(
                self.content(), pdf, temporary_directory
            )
            with draft_path.open("rb") as draft:
                message = self.parse_draft(draft.read())

            self.assertEqual(draft_path.parent, Path(temporary_directory))
            self.assertTrue(draft_path.name.startswith(mail_compose.DRAFT_PREFIX))
            self.assertEqual(draft_path.suffix, ".eml")
            self.assertEqual(message["X-Unsent"], "1")
            self.assertEqual(len(list(message.iter_attachments())), 1)

    def test_open_draft_uses_eml_argument_no_shell_and_no_console(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            pdf = Path(temporary_directory) / "reminder.pdf"
            pdf.write_bytes(b"pdf")
            executable = r"C:\Program Files\Mozilla Thunderbird\thunderbird.exe"
            write_draft = mail_compose.write_thunderbird_draft
            with patch.object(mail_compose, "cleanup_stale_thunderbird_drafts"):
                with patch.object(
                    mail_compose,
                    "write_thunderbird_draft",
                    side_effect=lambda content, path: write_draft(
                        content, path, temporary_directory
                    ),
                ):
                    with patch.object(mail_compose.sys, "platform", "win32"):
                        with patch.object(mail_compose.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
                            with patch.object(mail_compose.subprocess, "Popen") as popen:
                                popen.return_value.poll.return_value = None
                                opened = mail_compose.open_thunderbird_draft(
                                    executable, self.content(), pdf
                                )

            self.assertTrue(opened)
            command = popen.call_args.args[0]
            self.assertEqual(len(command), 2)
            self.assertEqual(command[0], executable)
            draft_path = Path(command[1])
            self.assertEqual(draft_path.suffix, ".eml")
            self.assertTrue(draft_path.is_file())
            message = self.parse_draft(draft_path.read_bytes())
            self.assertEqual(message["X-Unsent"], "1")
            self.assertEqual(len(list(message.iter_attachments())), 1)
            self.assertNotIn("shell", popen.call_args.kwargs)
            self.assertEqual(popen.call_args.kwargs["stdin"], mail_compose.subprocess.DEVNULL)
            self.assertEqual(popen.call_args.kwargs["stdout"], mail_compose.subprocess.DEVNULL)
            self.assertEqual(popen.call_args.kwargs["stderr"], mail_compose.subprocess.DEVNULL)
            self.assertEqual(popen.call_args.kwargs["creationflags"], 0x08000000)

    def test_missing_pdf_never_starts_thunderbird(self):
        with patch.object(mail_compose, "cleanup_stale_thunderbird_drafts"):
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
            with patch.object(mail_compose, "cleanup_stale_thunderbird_drafts"):
                with patch.object(mail_compose.subprocess, "Popen") as popen:
                    with self.assertRaises(ValueError):
                        mail_compose.open_thunderbird_draft(
                            "thunderbird.exe", self.content(), pdf
                        )
        popen.assert_not_called()

    def test_immediate_thunderbird_failure_is_reported_and_draft_removed(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            pdf = Path(temporary_directory) / "reminder.pdf"
            pdf.write_bytes(b"pdf")
            write_draft = mail_compose.write_thunderbird_draft
            with patch.object(mail_compose, "cleanup_stale_thunderbird_drafts"):
                with patch.object(
                    mail_compose,
                    "write_thunderbird_draft",
                    side_effect=lambda content, path: write_draft(
                        content, path, temporary_directory
                    ),
                ):
                    with patch.object(mail_compose.subprocess, "Popen") as popen:
                        popen.return_value.poll.return_value = 2
                        with self.assertRaisesRegex(RuntimeError, "code 2"):
                            mail_compose.open_thunderbird_draft(
                                "thunderbird.exe", self.content(), pdf
                            )
            self.assertEqual(list(Path(temporary_directory).glob("*.eml")), [])

    def test_failed_draft_build_leaves_no_temporary_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            pdf = Path(temporary_directory) / "reminder.pdf"
            pdf.write_bytes(b"pdf")
            with patch.object(
                mail_compose, "build_thunderbird_draft", side_effect=RuntimeError("boom")
            ):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    mail_compose.write_thunderbird_draft(
                        self.content(), pdf, temporary_directory
                    )
            self.assertEqual(list(Path(temporary_directory).glob("*.eml")), [])

    def test_cleanup_removes_only_stale_paypamin_eml_drafts(self):
        now = 1_000_000
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            stale = directory / f"{mail_compose.DRAFT_PREFIX}old.eml"
            recent = directory / f"{mail_compose.DRAFT_PREFIX}recent.eml"
            unrelated = directory / "other-draft.eml"
            wrong_suffix = directory / f"{mail_compose.DRAFT_PREFIX}old.txt"
            for path in (stale, recent, unrelated, wrong_suffix):
                path.write_bytes(b"draft")
            old = now - mail_compose.DRAFT_MAX_AGE_SECONDS - 1
            os.utime(stale, (old, old))
            os.utime(unrelated, (old, old))
            os.utime(wrong_suffix, (old, old))
            os.utime(recent, (now, now))

            mail_compose.cleanup_stale_thunderbird_drafts(directory, now=now)

            self.assertFalse(stale.exists())
            self.assertTrue(recent.exists())
            self.assertTrue(unrelated.exists())
            self.assertTrue(wrong_suffix.exists())


if __name__ == "__main__":
    unittest.main()
