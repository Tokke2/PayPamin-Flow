"""Tests for local self-learning that never acts without explicit consent."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import learning
from test_database import load_headless_app


SUPPLIER_WORDS = (
    "nordic industri verkstad maskin service teknisk support reservdelar montage "
    "projektledning kvalitet arbetsmiljo logistik lager leverans fakturering ekonomi "
    "kundtjanst forsaljning produktion verktyg smide svets montering konstruktion "
    "elautomation driftsattning dokumentation utbildning konsult uppdrag avtal garanti "
    "serviceavtal underhall forebyggande felsokning installation idrifttagning "
    "programvara hardvara systemintegration matning kalibrering certifiering revision "
    "radgivning analys optimering effektivisering hallbarhet atervinning emballage "
    "transport spedition tulldeklaration inkop upphandling offert orderbekraftelse "
    "kreditvillkor projektnummer kostnadsstalle attest godkannande attestant bestallare"
)
UNRELATED_WORDS = (
    "sjukvard apotek vardcentral tandlakare medicin recept halsa patient journal lakare "
    "sjukskoterska laboratorium provtagning rontgen ultraljud operation kirurgi "
    "aterbesok remiss vardplan omsorg aldreomsorg hemtjanst personlig assistans "
    "funktionsstod habilitering rehabilitering fysioterapi arbetsterapi logoped dietist "
    "psykolog kurator socialtjanst myndighet tillstand inspektion tillsyn regelverk "
    "lagstiftning forordning patientsakerhet hygien smitta vaccination provsvar diagnos "
    "behandling vardkedja primarvard specialistvard akutmottagning intensivvard"
)


def supplier_text(words=SUPPLIER_WORDS, customer="Kund Ett AB", invoice_no="1001"):
    return f"Nordic Industri AB\n{words}\nFaktura {invoice_no} 2026-01-01 1 250,00 kund {customer}"


class LearningStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        learning.ensure_learning_schema(self.db)

    def observe(self, value, times, field="note", scope="Kund AB", kind=learning.KIND_CUSTOMER):
        for _ in range(times):
            learning.record(self.db, kind, scope, field, value, scope_label=scope)

    def test_two_consistent_saves_are_offered_but_not_applied(self):
        self.observe("Avser konsultuppdrag", 2)

        learned = learning.recommend(self.db, learning.KIND_CUSTOMER, "Kund AB", "note")

        self.assertIsNotNone(learned)
        self.assertEqual(learned.value, "Avser konsultuppdrag")
        self.assertEqual(learned.observations, 2)
        self.assertFalse(hasattr(learned, "automatic"))

    def test_heavy_evidence_is_still_only_a_suggestion(self):
        self.observe("Avser konsultuppdrag", 40)

        learned = learning.recommend(self.db, learning.KIND_CUSTOMER, "kund ab", "note")

        self.assertIsNotNone(learned)
        self.assertEqual(learned.observations, 40)
        self.assertFalse(hasattr(learned, "automatic"))

    def test_no_amount_of_evidence_turns_a_value_into_a_decision(self):
        for _ in range(200):
            self.observe("Avser konsultuppdrag", 1)

        learned = learning.recommend(self.db, learning.KIND_CUSTOMER, "Kund AB", "note")

        self.assertIsNotNone(learned)
        self.assertGreater(learned.observations, 100)
        self.assertFalse(hasattr(learned, "automatic"))

    def test_ambiguous_evidence_is_never_applied(self):
        self.observe("Avser A", 2)
        self.observe("Avser B", 2)

        self.assertIsNone(learning.recommend(self.db, learning.KIND_CUSTOMER, "Kund AB", "note"))

    def test_one_observation_is_not_enough_for_a_suggestion(self):
        self.observe("Avser engångsjobb", 1)

        self.assertIsNone(learning.recommend(self.db, learning.KIND_CUSTOMER, "Kund AB", "note"))

    def test_blank_values_never_erase_learning(self):
        self.observe("Avser konsultuppdrag", 3)
        self.assertFalse(learning.record(self.db, learning.KIND_CUSTOMER, "Kund AB", "note", "   "))

        learned = learning.recommend(self.db, learning.KIND_CUSTOMER, "Kund AB", "note")

        self.assertIsNotNone(learned)
        self.assertEqual(learned.observations, 3)

    def test_a_declined_suggestion_returns_after_more_evidence(self):
        self.observe("Avser konsultuppdrag", 2)
        learned = learning.recommend(self.db, learning.KIND_CUSTOMER, "Kund AB", "note")
        learning.decline(self.db, learned)

        self.assertIsNone(learning.recommend(self.db, learning.KIND_CUSTOMER, "Kund AB", "note"))

        self.observe("Avser konsultuppdrag", 2)
        again = learning.recommend(self.db, learning.KIND_CUSTOMER, "Kund AB", "note")
        self.assertIsNotNone(again)
        self.assertEqual(again.observations, 4)

    def test_forget_removes_one_value_or_everything(self):
        self.observe("Avser A", 2)
        self.observe("Avser B", 2)
        self.observe("EUR", 2, field="currency")

        removed = learning.forget(self.db, kind=learning.KIND_CUSTOMER, scope="Kund AB", field="note", value="Avser A")
        self.assertEqual(removed, 1)
        self.assertEqual(len(learning.entries(self.db)), 2)

        learning.forget(self.db)
        self.assertEqual(learning.entries(self.db), [])
        self.assertEqual(learning.counts(self.db)["values"], 0)

    def test_entries_describe_evidence_without_a_decision_mode(self):
        self.observe("Avser A", 3)
        self.observe("Avser B", 1)

        entry = next(item for item in learning.entries(self.db) if item.value == "Avser A")

        self.assertEqual((entry.observations, entry.total), (3, 4))
        self.assertFalse(hasattr(entry, "automatic"))

    def test_signature_is_learned_and_matches_a_later_invoice(self):
        self.assertTrue(learning.record_supplier_signature(self.db, "Nordic Industri AB", supplier_text()))

        matched = learning.match_supplier_signature(
            self.db, supplier_text(customer="Annan Kund AB", invoice_no="9999")
        )

        self.assertIsNotNone(matched)
        self.assertEqual(matched.vendor, "Nordic Industri AB")
        self.assertGreaterEqual(matched.similarity, learning.SUPPLIER_SUGGEST_SIMILARITY)

    def test_unrelated_invoice_does_not_match_a_learned_supplier(self):
        learning.record_supplier_signature(self.db, "Nordic Industri AB", supplier_text())

        self.assertIsNone(learning.match_supplier_signature(self.db, supplier_text(UNRELATED_WORDS)))

    def test_near_identical_layout_is_not_stored_twice(self):
        self.assertTrue(learning.record_supplier_signature(self.db, "Nordic Industri AB", supplier_text()))
        self.assertFalse(
            learning.record_supplier_signature(
                self.db, "Nordic Industri AB", supplier_text(customer="Annan Kund AB", invoice_no="1002")
            )
        )
        self.assertEqual(learning.counts(self.db)["signatures"], 1)

    def test_short_or_empty_text_is_not_learned(self):
        self.assertFalse(learning.record_supplier_signature(self.db, "Liten AB", "Faktura 12"))
        self.assertIsNone(learning.match_supplier_signature(self.db, "Faktura 12"))


class InvoiceLearningIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "learning.sqlite3"
        self.app.init_db()
        self.addCleanup(self._close_handlers)

    def _close_handlers(self):
        for handler in self.app.logger.handlers[:]:
            self.app.logger.removeHandler(handler)
            handler.close()

    def invoice(self, number, **overrides):
        values = {
            "customer": "Kund AB",
            "invoice_no": number,
            "invoice_date": "2026-01-01",
            "due_date": "2026-01-31",
            "template_vendor": "",
            "amount": 1000.0,
            "currency": "SEK",
            "paid": 0,
            "email": "",
            "source": "",
            "source_hash": "",
            "note": "",
            "reviewed": 1,
            "logo_file": None,
        }
        values.update(overrides)
        return values

    def defaults(self, **overrides):
        values = {
            "customer": "Kund AB",
            "invoice_date": "2026-02-01",
            "due_date": "",
            "template_vendor": "",
            "currency": "",
            "email": "",
            "note": "",
            "logo_file": None,
        }
        values.update(overrides)
        return self.app.learned_invoice_defaults(values)

    def test_two_saved_invoices_offer_customer_defaults(self):
        for number in ("L-1", "L-2"):
            self.app.save_invoice_record(self.invoice(number, currency="EUR", note="Avser konsult"))

        values, suggested = self.defaults()

        self.assertEqual({item.field for item in suggested}, {"currency", "note"})
        self.assertEqual(values["currency"], "")
        self.assertEqual(values["note"], "")

    def test_many_saved_invoices_still_never_fill_a_field(self):
        for number in range(25):
            self.app.save_invoice_record(
                self.invoice(f"L-{number}", currency="EUR", note="Avser konsult")
            )

        values, suggested = self.defaults()

        # The app suggests, but never decides: the form stays empty.
        self.assertEqual(values["currency"], "")
        self.assertEqual(values["note"], "")
        self.assertEqual(values["email"], "")
        self.assertEqual({item.field for item in suggested}, {"currency", "note"})
        self.assertTrue(all(item.observations >= 25 for item in suggested))

    def test_supplier_payment_term_is_suggested_but_not_applied(self):
        for number in range(10):
            self.app.save_invoice_record(
                self.invoice(f"L-{number}", template_vendor="Leverantör AB", due_date="2026-01-31")
            )

        values, suggested = self.defaults(template_vendor="Leverantör AB")

        self.assertEqual(values["due_date"], "")
        self.assertIn("payment_term_days", {item.field for item in suggested})

    def test_startup_and_learning_are_enabled_on_a_fresh_database(self):
        self.assertEqual(self.app.setting("start_minimized"), "1")
        self.assertEqual(self.app.setting("learning_enabled"), "1")

    def test_disabled_learning_records_and_suggests_nothing(self):
        self.app.set_setting("learning_enabled", "0")
        for number in ("L-1", "L-2", "L-3"):
            self.app.save_invoice_record(self.invoice(number, currency="EUR", note="Avser konsult"))

        values, suggested = self.defaults()

        self.assertEqual((suggested, values["currency"]), ([], ""))
        with self.app.connect() as db:
            self.assertEqual(self.app.learning.entries(db), [])

    def test_learning_failure_never_blocks_a_saved_invoice(self):
        with patch.object(self.app, "record_invoice_learning_db", side_effect=RuntimeError("synthetic")):
            duplicate = self.app.save_invoice_record(self.invoice("L-9"))

        self.assertIsNone(duplicate)
        with self.app.connect() as db:
            saved = db.execute("SELECT invoice_no FROM invoices WHERE invoice_no='L-9'").fetchone()
        self.assertIsNotNone(saved)

    def test_learned_recipients_are_reused_when_the_contact_is_empty(self):
        row = {"customer": "Kund AB", "email": ""}
        self.app.record_reminder_learning(row, ["faktura@kund.se", "ekonomi@kund.se"])
        self.app.record_reminder_learning(row, ["faktura@kund.se", "ekonomi@kund.se"])

        self.assertEqual(
            self.app.reminder_email_addresses(row), ["faktura@kund.se", "ekonomi@kund.se"]
        )

    def test_confirmed_supplier_layout_only_prefills_the_review_dialog(self):
        self.assertTrue(self.app.record_supplier_learning("Nordic Industri AB", supplier_text()))
        fake = SimpleNamespace(_supplier_learning_note=None)

        vendor = self.app.ReminderApp.guess_supplier(
            fake, supplier_text(customer="Ny Kund AB", invoice_no="7777")
        )

        self.assertEqual(vendor, "Nordic Industri AB")
        # The note carries the similarity only; there is no automatic flag.
        self.assertEqual(len(fake._supplier_learning_note), 2)

    def test_even_overwhelming_evidence_is_asked_as_a_question(self):
        learned = learning.LearnedValue(
            kind=learning.KIND_CUSTOMER, scope="kund ab", scope_label="Kund AB",
            field="currency", value="EUR", observations=100, total=100,
        )
        asked = {}

        def ask(title, message, parent=None):
            asked["title"] = title
            asked["message"] = message
            return False

        with patch.object(self.app.messagebox, "askyesno", side_effect=ask, create=True):
            accepted = self.app.ReminderApp._confirm_learned_suggestions(
                SimpleNamespace(), [learned], None
            )

        self.assertFalse(accepted)
        self.assertEqual(asked["title"], "Inlärda förslag")
        self.assertIn("(100 gånger)", asked["message"])
        self.assertIn("aldrig", asked["message"])

    def test_learning_is_local_to_the_database(self):
        self.app.save_invoice_record(self.invoice("L-1", note="Avser konsult"))
        with self.app.connect() as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("learning_values", tables)
        self.assertIn("learning_signatures", tables)


if __name__ == "__main__":
    unittest.main()
