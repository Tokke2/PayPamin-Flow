import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, unquote, urlsplit

from customer_contacts import EmailAddressError, normalize_email_addresses, parse_email_addresses
from reminder_journal import import_journal
from test_database import load_headless_app


class CustomerContactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "contacts.sqlite3"
        self.app.JOURNAL_PATH = self.workspace / "reminder_journal.json"
        self.app.EXPORT_DIR = self.workspace / "export"
        self.app.EXPORT_DIR.mkdir(exist_ok=True)
        self.app.init_db()
        self.app.set_language("sv")

        def cleanup():
            self.app.set_language("sv")
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def record(self, invoice_no="CONTACT-1001", email=""):
        return {
            "customer": "Testkund AB",
            "invoice_no": invoice_no,
            "invoice_date": "2026-09-01",
            "due_date": "2000-01-01",
            "template_vendor": "",
            "amount": 1250.0,
            "currency": "SEK",
            "paid": 0,
            "email": email,
            "source": "",
            "source_hash": "source-" + invoice_no,
            "note": "",
            "reviewed": 1,
            "logo_file": "",
        }

    def existing_p1(self, email=""):
        self.assertIsNone(self.app.save_invoice_record(self.record(email=email)))
        with self.app.connect() as db:
            row = db.execute("SELECT * FROM invoices").fetchone()
        snapshot = self.app.capture_p1_snapshot(row, 150.0, "2026-10-01")
        with self.app.connect() as db:
            db.execute(
                "UPDATE invoices SET p1_date='2026-10-01',p1_snapshot=?,sent_count=1",
                (snapshot,),
            )
            row = db.execute("SELECT * FROM invoices").fetchone()
        pdf_path = self.app.reminder_file_path(row, "P1", date(2026, 10, 1), "paminnelse")
        pdf_path.write_bytes(b"existing P1")
        return row, pdf_path

    def test_comma_separated_addresses_are_trimmed_and_deduplicated(self):
        value = " first@example.com, second@example.com , FIRST@example.com,,"
        self.assertEqual(
            parse_email_addresses(value),
            ["first@example.com", "second@example.com"],
        )
        self.assertEqual(
            normalize_email_addresses(value),
            "first@example.com, second@example.com",
        )

    def test_invalid_address_is_rejected(self):
        with self.assertRaises(EmailAddressError) as raised:
            parse_email_addresses("valid@example.com, not-an-email")
        self.assertEqual(raised.exception.address, "not-an-email")
        with self.assertRaises(EmailAddressError):
            parse_email_addresses("missing-domain@example")

    def test_invoice_save_learns_and_reuses_customer_recipients(self):
        self.assertIsNone(self.app.save_invoice_record(self.record(
            email="first@example.com, second@example.com"
        )))
        values = self.app.apply_saved_customer_contact({
            "customer": "  testkund   ab ", "email": "",
        })
        self.assertEqual(values["email"], "first@example.com, second@example.com")

        edited = self.record(email="new@example.com")
        with self.app.connect() as db:
            row_id = db.execute("SELECT id FROM invoices WHERE invoice_no='CONTACT-1001'").fetchone()[0]
        self.assertIsNone(self.app.save_invoice_record(edited, row_id))
        values = self.app.apply_saved_customer_contact({"customer": "Testkund AB", "email": "old@example.com"})
        self.assertEqual(values["email"], "new@example.com")

    def test_invalid_invoice_email_rolls_back_invoice_and_contact(self):
        with self.assertRaises(EmailAddressError):
            self.app.save_invoice_record(self.record(email="invalid-address"))
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM customer_contacts").fetchone()[0], 0)

    def test_customer_contacts_are_included_in_json_and_restored_without_overwriting_local_edits(self):
        self.assertIsNone(self.app.save_invoice_record(self.record(
            email="first@example.com, second@example.com"
        )))
        self.assertTrue(self.app.refresh_json_journal())
        payload = json.loads(self.app.JOURNAL_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["customer_contacts"][0]["emails"], "first@example.com, second@example.com")

        source_db = self.app.DB_PATH
        source_json = self.app.JOURNAL_PATH
        target_db = self.workspace / "restored.sqlite3"
        target_json = self.workspace / "restored.json"
        self.app.DB_PATH = target_db
        self.app.init_db()
        import_journal(target_db, target_json, source_json)
        with self.app.connect() as db:
            db.execute("UPDATE customer_contacts SET emails='local@example.com'")
        import_journal(target_db, target_json, source_json)
        with closing(sqlite3.connect(target_db)) as db:
            rows = db.execute("SELECT customer_name,emails FROM customer_contacts").fetchall()
        self.assertEqual(rows, [("Testkund AB", "local@example.com")])
        self.assertTrue(source_db.is_file())

    def test_mailto_contains_all_recipients_subject_and_body(self):
        row = self.record(email="first@example.com, second@example.com")
        url = self.app.build_reminder_mailto(
            row, "P1", ["first@example.com", "second@example.com"]
        )
        parsed = urlsplit(url)
        self.assertEqual(parsed.scheme, "mailto")
        self.assertEqual(unquote(parsed.path), "first@example.com,second@example.com")
        query = parse_qs(parsed.query)
        self.assertIn("CONTACT-1001", query["subject"][0])
        self.assertNotIn("SV:", query["subject"][0])
        self.assertEqual(query["bcc"], ["rl@tadega.com"])
        self.assertNotIn("rl@tadega.com", unquote(parsed.path))
        body = query["body"][0]
        self.assertIn("första påminnelsen", body)
        self.assertIn("250", body)
        self.assertIn("kr", body)
        self.assertIn("Tadega AB", body)
        self.assertNotIn("attachment", query)

    def test_p2_has_reply_subject_custom_text_and_the_same_bcc(self):
        row = self.record(email="first@example.com")
        parsed = urlsplit(self.app.build_reminder_mailto(row, "P2", ["first@example.com"]))
        query = parse_qs(parsed.query)
        self.assertTrue(query["subject"][0].startswith("SV: Faktura CONTACT-1001"))
        self.assertEqual(query["bcc"], ["rl@tadega.com"])
        body = query["body"][0]
        self.assertIn("andra påminnelsen", body)
        self.assertIn("P1 och P2", body)
        self.assertIn("Sista betalningsdag", body)

        self.app.set_language("en")
        parsed = urlsplit(self.app.build_reminder_mailto(row, "P2", ["first@example.com"]))
        query = parse_qs(parsed.query)
        self.assertTrue(query["subject"][0].startswith("Re: Invoice CONTACT-1001"))
        self.assertIn("second reminder", query["body"][0])

    def test_p1_email_uses_original_snapshot_terms_and_amounts(self):
        row = self.record(email="first@example.com")
        self.app.set_setting("fee", "150")
        self.app.set_setting("payment_deadline_days", "10")
        row["sent_count"] = 0
        snapshot = self.app.capture_p1_snapshot(row, 150.0, "2026-10-01")
        row["p1_date"] = "2026-10-01"
        row["p1_snapshot"] = snapshot
        row["sent_count"] = 1
        row["amount"] = 9999.0
        self.app.set_setting("fee", "999")
        self.app.set_setting("payment_deadline_days", "30")

        query = parse_qs(urlsplit(self.app.build_reminder_mailto(
            row, "P1", ["first@example.com"]
        )).query)
        body = query["body"][0].replace("\xa0", " ")
        self.assertIn("1 400,00", body)
        self.assertNotIn("10 149", body)
        self.assertIn(self.app.format_long_date(date(2026, 10, 11)), body)
        self.assertTrue(query["subject"][0].startswith("SV: Faktura CONTACT-1001"))
        self.assertEqual(query["bcc"], ["rl@tadega.com"])

    def test_p2_email_uses_original_snapshot_terms_amounts_and_deadline(self):
        row = self.record(email="first@example.com")
        row["p1_date"] = "2026-10-01"
        self.app.set_setting("payment_deadline_days", "10")
        snapshot = self.app.capture_reminder_snapshot(row, 150.0, "2026-10-10", "P2")
        row["p2_date"] = "2026-10-10"
        row["p2_snapshot"] = snapshot
        row["sent_count"] = 2
        row["amount"] = 9999.0
        self.app.set_setting("fee", "999")
        self.app.set_setting("payment_deadline_days", "30")

        query = parse_qs(urlsplit(self.app.build_reminder_mailto(
            row, "P2", ["first@example.com"]
        )).query)

        body = query["body"][0].replace("\xa0", " ")
        self.assertIn("1 550,00", body)
        self.assertNotIn("10 299", body)
        self.assertIn(self.app.format_long_date(date(2026, 10, 20)), body)
        self.assertNotIn(self.app.format_long_date(date(2026, 11, 9)), body)
        self.assertTrue(query["subject"][0].startswith("SV: Faktura CONTACT-1001"))
        self.assertEqual(query["bcc"], ["rl@tadega.com"])

    def test_context_email_uses_addresses_added_after_p1_without_new_history(self):
        row, pdf_path = self.existing_p1()
        edited = self.record(email="late@example.com, second@example.com")
        self.assertIsNone(self.app.save_invoice_record(edited, row["id"]))
        with self.app.connect() as db:
            row = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
            before = db.execute(
                "SELECT p1_date,p2_date,sent_count,p1_snapshot FROM invoices WHERE id=?",
                (row["id"],),
            ).fetchone()
        owner = SimpleNamespace(selected=lambda: row)
        owner.open_reminder_email = MethodType(self.app.ReminderApp.open_reminder_email, owner)

        with patch.object(self.app.webbrowser, "open", return_value=True) as open_url:
            opened = self.app.ReminderApp.create_reminder_email(owner)

        self.assertTrue(opened)
        parsed = urlsplit(open_url.call_args.args[0])
        query = parse_qs(parsed.query)
        self.assertEqual(unquote(parsed.path), "late@example.com,second@example.com")
        self.assertEqual(query["bcc"], ["rl@tadega.com"])
        self.assertIn("första påminnelsen", query["body"][0])
        self.assertEqual(pdf_path.read_bytes(), b"existing P1")
        with self.app.connect() as db:
            after = db.execute(
                "SELECT p1_date,p2_date,sent_count,p1_snapshot FROM invoices WHERE id=?",
                (row["id"],),
            ).fetchone()
            event_count = db.execute("SELECT COUNT(*) FROM reminder_events").fetchone()[0]
        self.assertEqual(tuple(after), tuple(before))
        self.assertEqual(event_count, 0)

    def test_context_email_prefers_p2_and_finds_archived_pdf(self):
        row, _ = self.existing_p1(email="current@example.com")
        snapshot = self.app.capture_reminder_snapshot(row, 150.0, "2026-10-10", "P2")
        with self.app.connect() as db:
            db.execute(
                "UPDATE invoices SET p2_date='2026-10-10',p2_snapshot=?,sent_count=2 WHERE id=?",
                (snapshot, row["id"]),
            )
            row = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        pdf_path = self.app.reminder_file_path(row, "P2", date(2026, 10, 10), "paminnelse")
        pdf_path = pdf_path.parent / self.app.ARCHIVE_FOLDER_NAME / pdf_path.name
        pdf_path.parent.mkdir(exist_ok=True)
        pdf_path.write_bytes(b"archived P2")
        owner = SimpleNamespace(selected=lambda: row, open_reminder_email=Mock(return_value=True))

        opened = self.app.ReminderApp.create_reminder_email(owner)

        self.assertTrue(opened)
        self.assertEqual(
            owner.open_reminder_email.call_args.args[1:],
            ("P2", pdf_path),
        )
        with self.app.connect() as db:
            saved = db.execute(
                "SELECT p1_date,p2_date,sent_count,p2_snapshot FROM invoices WHERE id=?",
                (row["id"],),
            ).fetchone()
        self.assertEqual(tuple(saved), ("2026-10-01", "2026-10-10", 2, snapshot))

    def test_context_email_uses_legacy_event_path_and_current_customer_contact(self):
        row, _ = self.existing_p1(email="old@example.com")
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET p2_date='2026-10-10',sent_count=2")
            row = db.execute("SELECT * FROM invoices").fetchone()
        pdf_path = self.app.reminder_file_path(row, "P2", date(2026, 10, 10), "paminnelse")
        pdf_path.write_bytes(b"legacy P2")
        self.app.record_reminder_journal(
            self.app.DB_PATH, self.app.JOURNAL_PATH, row["id"], "P2", "2026-10-10",
            150.0, self.app.current_reminder_terms(150.0), "sv", "", pdf_path.name,
        )
        edited = self.record(email="new@example.com")
        edited["customer"] = "Renamed customer AB"
        self.assertIsNone(self.app.save_invoice_record(edited, row["id"]))
        with self.app.connect() as db:
            row = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(row["p2_snapshot"], "")
        owner = SimpleNamespace(selected=lambda: row, open_reminder_email=Mock(return_value=True))

        opened = self.app.ReminderApp.create_reminder_email(owner)

        self.assertTrue(opened)
        self.assertEqual(owner.open_reminder_email.call_args.args[1:], ("P2", pdf_path))
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM reminder_events").fetchone()[0], 1)

    def test_context_email_without_addresses_explains_edit_customer(self):
        row, _ = self.existing_p1()
        owner = SimpleNamespace(selected=lambda: row, open_reminder_email=Mock())
        with patch.object(self.app.messagebox, "showinfo", create=True) as info:
            opened = self.app.ReminderApp.create_reminder_email(owner)
        self.assertFalse(opened)
        owner.open_reminder_email.assert_not_called()
        self.assertIn("Redigera kund", info.call_args.args[1])

    def test_context_email_requires_existing_pdf_without_creating_history(self):
        row, pdf_path = self.existing_p1(email="current@example.com")
        pdf_path.unlink()
        owner = SimpleNamespace(selected=lambda: row, open_reminder_email=Mock())
        with patch.object(self.app.messagebox, "showwarning", create=True) as warning:
            opened = self.app.ReminderApp.create_reminder_email(owner)
        self.assertFalse(opened)
        owner.open_reminder_email.assert_not_called()
        self.assertIn("Redigera P1", warning.call_args.args[1])
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT sent_count FROM invoices").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM reminder_events").fetchone()[0], 0)

    def test_generated_reminder_opens_default_email_app_for_all_customer_addresses(self):
        self.assertIsNone(self.app.save_invoice_record(self.record(
            email="first@example.com, second@example.com"
        )))
        with self.app.connect() as db:
            row = db.execute("SELECT * FROM invoices").fetchone()
        owner = SimpleNamespace()
        with patch.object(self.app.webbrowser, "open", return_value=True) as open_url:
            opened = self.app.ReminderApp.open_reminder_email(
                owner, row, "P1", self.workspace / "reminder.pdf"
            )
        self.assertTrue(opened)
        url = open_url.call_args.args[0]
        self.assertEqual(unquote(urlsplit(url).path), "first@example.com,second@example.com")

    def test_no_customer_addresses_means_no_email_app_is_opened(self):
        self.assertIsNone(self.app.save_invoice_record(self.record(email="")))
        with self.app.connect() as db:
            row = db.execute("SELECT * FROM invoices").fetchone()
        with patch.object(self.app.webbrowser, "open") as open_url:
            opened = self.app.ReminderApp.open_reminder_email(
                SimpleNamespace(), row, "P1", self.workspace / "reminder.pdf"
            )
        self.assertFalse(opened)
        open_url.assert_not_called()

    def test_existing_database_is_migrated_with_email_status_columns(self):
        legacy_db = self.workspace / "legacy.sqlite3"
        with closing(sqlite3.connect(legacy_db)) as db:
            db.execute("CREATE TABLE invoices (id INTEGER PRIMARY KEY, invoice_no TEXT NOT NULL)")
        original_db = self.app.DB_PATH
        self.app.DB_PATH = legacy_db
        try:
            self.app.init_db()
        finally:
            self.app.DB_PATH = original_db
        with closing(sqlite3.connect(legacy_db)) as db:
            columns = {row[1] for row in db.execute("PRAGMA table_info(invoices)")}
        self.assertTrue({
            "p1_draft_date", "p2_draft_date", "p1_sent_date", "p2_sent_date",
        }.issubset(columns))

    def test_cancelled_email_preview_opens_nothing_and_records_nothing(self):
        row, pdf_path = self.existing_p1(email="current@example.com")
        owner = SimpleNamespace(
            preview_reminder_email=Mock(return_value=None), refresh=Mock(),
        )
        with patch.object(self.app.webbrowser, "open") as open_url:
            opened = self.app.ReminderApp.open_reminder_email(owner, row, "P1", pdf_path)
        self.assertFalse(opened)
        open_url.assert_not_called()
        owner.preview_reminder_email.assert_called_once()
        owner.refresh.assert_not_called()
        with self.app.connect() as db:
            status = db.execute(
                "SELECT p1_draft_date,p2_draft_date,p1_sent_date,p2_sent_date,sent_count FROM invoices"
            ).fetchone()
            self.assertEqual(tuple(status), ("", "", "", "", 1))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM reminder_events").fetchone()[0], 0)

    def test_failed_mailto_opening_records_no_draft_status(self):
        row, pdf_path = self.existing_p1(email="current@example.com")
        owner = SimpleNamespace(
            preview_reminder_email=Mock(side_effect=lambda content, path: content), refresh=Mock(),
        )
        with patch.object(self.app.webbrowser, "open", return_value=False):
            with patch.object(self.app.messagebox, "showwarning", create=True) as warning:
                opened = self.app.ReminderApp.open_reminder_email(owner, row, "P1", pdf_path)
        self.assertFalse(opened)
        warning.assert_called_once()
        owner.refresh.assert_not_called()
        with self.app.connect() as db:
            status = db.execute(
                "SELECT p1_draft_date,p2_draft_date,p1_sent_date,p2_sent_date,sent_count FROM invoices"
            ).fetchone()
            self.assertEqual(tuple(status), ("", "", "", "", 1))

    def test_accepted_email_preview_uses_temporary_edits_and_records_draft(self):
        row, pdf_path = self.existing_p1(email="first@example.com, second@example.com")

        def edit_preview(content, shown_path):
            self.assertEqual(content["recipients"], ["first@example.com", "second@example.com"])
            self.assertEqual(content["bcc"], "rl@tadega.com")
            self.assertEqual(shown_path, pdf_path)
            edited = dict(content)
            edited["subject"] = "Tillfälligt ämne"
            edited["body"] = "Tillfälligt meddelande"
            return edited

        owner = SimpleNamespace(
            preview_reminder_email=Mock(side_effect=edit_preview), refresh=Mock(),
        )
        with patch.object(self.app.webbrowser, "open", return_value=True) as open_url:
            opened = self.app.ReminderApp.open_reminder_email(owner, row, "P1", pdf_path)
        self.assertTrue(opened)
        parsed = urlsplit(open_url.call_args.args[0])
        query = parse_qs(parsed.query)
        self.assertEqual(unquote(parsed.path), "first@example.com,second@example.com")
        self.assertEqual(query["bcc"], ["rl@tadega.com"])
        self.assertEqual(query["subject"], ["Tillfälligt ämne"])
        self.assertEqual(query["body"], ["Tillfälligt meddelande"])
        standard = self.app.build_reminder_email_content(
            row, "P1", ["first@example.com", "second@example.com"]
        )
        self.assertNotEqual(standard["subject"], "Tillfälligt ämne")
        self.assertNotEqual(standard["body"], "Tillfälligt meddelande")
        with self.app.connect() as db:
            saved = db.execute(
                "SELECT p1_draft_date,p2_draft_date,p1_sent_date,p2_sent_date,sent_count FROM invoices"
            ).fetchone()
            self.assertEqual(tuple(saved), (date.today().isoformat(), "", "", "", 1))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM reminder_events").fetchone()[0], 0)
        journal = json.loads(self.app.JOURNAL_PATH.read_text(encoding="utf-8"))
        self.assertEqual(journal["invoices"][0]["p1_draft_date"], date.today().isoformat())
        owner.refresh.assert_called_once()

    def test_email_status_is_per_level_and_always_shows_latest(self):
        row, _ = self.existing_p1(email="current@example.com")
        self.assertEqual(self.app.latest_reminder_level(row), "P1")
        self.assertEqual(self.app.reminder_email_status(row), "P1 · utkast ej öppnat")
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET p1_draft_date='2026-10-02'")
            row = db.execute("SELECT * FROM invoices").fetchone()
        self.assertEqual(self.app.reminder_email_status(row), "P1 · utkast öppnat 2026-10-02")
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET p1_sent_date='2026-10-03'")
            row = db.execute("SELECT * FROM invoices").fetchone()
        self.assertEqual(self.app.reminder_email_status(row), "P1 · skickad 2026-10-03")
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET p2_date='2026-10-10',sent_count=2")
            row = db.execute("SELECT * FROM invoices").fetchone()
        self.assertEqual(self.app.latest_reminder_level(row), "P2")
        self.assertEqual(self.app.reminder_email_status(row), "P2 · utkast ej öppnat")
        self.assertEqual(self.app.reminder_email_status(row, "P1"), "P1 · skickad 2026-10-03")
        self.assertEqual(row["p1_sent_date"], "2026-10-03")
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET p2_draft_date='2026-10-11',p2_sent_date='2026-10-12'")
            row = db.execute("SELECT * FROM invoices").fetchone()
        self.assertEqual(self.app.reminder_email_status(row), "P2 · skickad 2026-10-12")
        self.assertEqual(row["p1_draft_date"], "2026-10-02")

    def test_opening_p2_draft_preserves_p1_status_and_reminder_history(self):
        row, pdf_path = self.existing_p1(email="current@example.com")
        snapshot = self.app.capture_reminder_snapshot(row, 150.0, "2026-10-10", "P2")
        with self.app.connect() as db:
            db.execute(
                "UPDATE invoices SET p2_date='2026-10-10',p2_snapshot=?,sent_count=2,p1_draft_date='2026-10-02',p1_sent_date='2026-10-03' WHERE id=?",
                (snapshot, row["id"]),
            )
            row = db.execute("SELECT * FROM invoices").fetchone()
        owner = SimpleNamespace(
            preview_reminder_email=Mock(side_effect=lambda content, path: content), refresh=Mock(),
        )
        with patch.object(self.app.webbrowser, "open", return_value=True):
            opened = self.app.ReminderApp.open_reminder_email(owner, row, "P2", pdf_path)
        self.assertTrue(opened)
        with self.app.connect() as db:
            saved = db.execute(
                "SELECT p1_draft_date,p1_sent_date,p2_draft_date,p2_sent_date,p1_date,p2_date,sent_count,p1_snapshot,p2_snapshot FROM invoices"
            ).fetchone()
            self.assertEqual(
                tuple(saved),
                ("2026-10-02", "2026-10-03", date.today().isoformat(), "", "2026-10-01", "2026-10-10", 2, row["p1_snapshot"], snapshot),
            )
            self.assertEqual(db.execute("SELECT COUNT(*) FROM reminder_events").fetchone()[0], 0)

    def test_sent_status_requires_explicit_confirmation_and_changes_no_history(self):
        row, _ = self.existing_p1(email="current@example.com")
        owner = SimpleNamespace(selected=lambda: row, refresh=Mock())
        with patch.object(self.app.messagebox, "askyesno", return_value=False, create=True):
            marked = self.app.ReminderApp.mark_reminder_email_sent(owner)
        self.assertFalse(marked)
        owner.refresh.assert_not_called()
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT p1_sent_date FROM invoices").fetchone()[0], "")
        with patch.object(self.app.messagebox, "askyesno", return_value=True, create=True) as confirm:
            with patch.object(self.app.webbrowser, "open") as open_url:
                marked = self.app.ReminderApp.mark_reminder_email_sent(owner)
        self.assertTrue(marked)
        self.assertIn("inte kontrollera e-postprogrammet", confirm.call_args.args[1])
        open_url.assert_not_called()
        owner.refresh.assert_called_once()
        with self.app.connect() as db:
            saved = db.execute(
                "SELECT p1_sent_date,p2_sent_date,sent_count,p1_date,p2_date FROM invoices"
            ).fetchone()
            self.assertEqual(tuple(saved), (date.today().isoformat(), "", 1, "2026-10-01", ""))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM reminder_events").fetchone()[0], 0)
        journal = json.loads(self.app.JOURNAL_PATH.read_text(encoding="utf-8"))
        self.assertEqual(journal["invoices"][0]["p1_sent_date"], date.today().isoformat())


if __name__ == "__main__":
    unittest.main()
