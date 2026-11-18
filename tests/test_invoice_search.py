"""Search over the invoice list.

The search is deliberately made of pure functions on top of one row, so the
rules can be tested without a display: which fields are searched, how a query
is split, and what the status line says about the result. The integration test
at the end runs the real ``refresh`` against a real database.
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import i18n
from test_database import load_headless_app


class SearchQueryTests(unittest.TestCase):
    """Splitting what the user typed into fields and words."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.app = load_headless_app(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def split(self, query):
        return self.app.split_search_query(query)

    def test_words_are_split_on_any_whitespace(self):
        self.assertEqual(self.split("  anna   limo\t6475 "), ((None, "anna"), (None, "limo"), (None, "6475")))

    def test_an_empty_query_has_no_terms(self):
        for empty in ("", "   ", None, "\t\n"):
            with self.subTest(empty=empty):
                self.assertEqual(self.split(empty), ())

    def test_every_known_prefix_names_its_field_in_both_languages(self):
        pairs = {
            "kund:limo": "customer", "customer:limo": "customer",
            "nr:6475": "invoice_no", "faktura:6475": "invoice_no", "invoice:6475": "invoice_no",
            "belopp:1500": "amount", "amount:1500": "amount",
            "datum:2026-11": "date", "date:2026-11": "date", "förfaller:2026-11": "date", "due:2026-11": "date",
            "status:granska": "stage",
            "epost:anna@": "email", "e-post:anna@": "email", "email:anna@": "email",
            "not:ränta": "note", "note:ränta": "note",
            "valuta:sek": "currency", "currency:sek": "currency",
        }
        for query, field in pairs.items():
            with self.subTest(query=query):
                self.assertEqual(self.split(query), ((field, query.split(":", 1)[1].lower()),))

    def test_a_prefix_is_case_insensitive(self):
        self.assertEqual(self.split("KUND:Limoeurope"), (("customer", "limoeurope"),))

    def test_an_unknown_prefix_stays_plain_text_instead_of_matching_nothing(self):
        self.assertEqual(self.split("fakturanr:6475"), ((None, "fakturanr:6475"),))

    def test_quotes_keep_a_customer_name_with_spaces_together(self):
        self.assertEqual(self.split('kund:"Acme AB" betalt'), (("customer", "acme ab"), (None, "betalt")))
        self.assertEqual(self.split('"Acme AB"'), ((None, "acme ab"),))

    def test_an_unclosed_quote_still_searches(self):
        self.assertEqual(self.split('kund:"Acme'), (("customer", "acme"),))

    def test_extra_spaces_inside_a_term_are_collapsed(self):
        self.assertEqual(self.split('"Acme    AB"'), ((None, "acme ab"),))


class SearchFieldTests(unittest.TestCase):
    """What each field contains for one invoice."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.app = load_headless_app(Path(cls.temporary.name))

    def setUp(self):
        self.row = {
            "customer": "Limoeurope AB", "invoice_no": "6475", "email": "anna@limoeurope.se",
            "note": "Avgift per påminnelse enligt avtal.", "currency": "SEK",
            "amount": 1500.0, "paid": 500.0, "due_date": "2026-11-01",
            "invoice_date": "2026-10-01", "p1_date": "2026-11-06", "p2_date": "",
        }
        i18n.set_language("sv")
        self.addCleanup(i18n.set_language, "sv")

    def fields(self, row=None, stage="P2 att skapa", remaining=None):
        return self.app.invoice_search_fields(row or self.row, stage, remaining)

    def matches(self, query, **options):
        return self.app.invoice_matches_search(self.fields(**options), self.app.split_search_query(query))

    def test_every_visible_field_is_searchable(self):
        for query in ("limoeurope", "6475", "anna@", "påminnelse", "sek", "2026-11-01", "p2 att skapa"):
            with self.subTest(query=query):
                self.assertTrue(self.matches(query))

    def test_a_prefix_only_searches_its_own_field(self):
        # "sek" is the currency and never the customer, and the other way round.
        self.assertTrue(self.matches("valuta:sek"))
        self.assertFalse(self.matches("kund:sek"))
        self.assertTrue(self.matches("kund:limo"))
        self.assertFalse(self.matches("epost:6475"))
        self.assertTrue(self.matches("epost:anna@"))

    def test_several_words_must_all_be_found_and_may_sit_in_different_fields(self):
        self.assertTrue(self.matches("limoeurope 6475 sek"))
        self.assertFalse(self.matches("limoeurope 9999"))

    def test_the_amount_is_found_in_every_spelling(self):
        for query in ("1500", "1500,00", "1500.00", "1 500,00", "1,500.00"):
            with self.subTest(query=query):
                self.assertTrue(self.matches(f"belopp:{query}"))
        # The remaining amount (1000 kr) is searchable too, not only the total.
        self.assertTrue(self.matches("belopp:1000"))

    def test_dates_are_found_as_stored_and_as_written_out(self):
        self.assertTrue(self.matches("datum:2026-11-01"))
        self.assertTrue(self.matches("datum:1 november 2026"))
        self.assertTrue(self.matches('datum:"november 2026"'))
        self.assertFalse(self.matches("datum:2027"))

    def test_the_stage_is_found_in_both_languages(self):
        self.assertTrue(self.matches("status:p2"))
        i18n.set_language("en")
        self.assertTrue(self.matches("status:p2"))
        self.assertTrue(self.matches("status:create"))
        self.assertFalse(self.matches("status:granska"))

    def test_a_missing_field_never_raises(self):
        bare = {"customer": "Acme", "invoice_no": "1"}
        fields = self.fields(row=bare)
        self.assertEqual(fields["email"], "")
        self.assertTrue(self.app.invoice_matches_search(fields, self.app.split_search_query("acme")))

    def test_an_empty_query_matches_every_row(self):
        self.assertTrue(self.app.invoice_matches_search(self.fields(), ()))

    def test_the_search_never_changes_the_row(self):
        before = dict(self.row)
        self.fields()
        self.assertTrue(self.matches("limoeurope"))
        self.assertEqual(self.row, before)


class SearchSummaryTests(unittest.TestCase):
    """The line under the tabs."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.app = load_headless_app(Path(cls.temporary.name))

    def setUp(self):
        i18n.set_language("sv")
        self.addCleanup(i18n.set_language, "sv")

    def summary(self, *args, **kwargs):
        return self.app.invoice_search_summary(*args, **kwargs)

    def test_without_a_query_it_counts_the_view(self):
        self.assertEqual(self.summary(4, 12), "Visar 4 av 12")

    def test_a_query_names_what_was_searched(self):
        self.assertEqual(self.summary(2, 12, "limo"), "Visar 2 av 12 · sökning: limo")

    def test_hits_in_another_view_are_named(self):
        self.assertEqual(self.summary(2, 12, "limo", 3), "Visar 2 av 12 · sökning: limo · 3 träffar i andra vyer")
        self.assertEqual(self.summary(2, 12, "limo", 1), "Visar 2 av 12 · sökning: limo · 1 träff i andra vyer")

    def test_an_empty_view_says_so_instead_of_showing_nothing(self):
        self.assertEqual(self.summary(0, 12, "saknas"), "Inga träffar för ”saknas”")
        self.assertEqual(self.summary(0, 12, "limo", 2), "Inga träffar i den här vyn · 2 träffar i andra vyer")
        self.assertEqual(self.summary(0, 12, "limo", 1), "Inga träffar i den här vyn · 1 träff i andra vyer")

    def test_the_line_is_translated(self):
        i18n.set_language("en")
        self.assertEqual(self.summary(2, 12, "limo"), "Showing 2 of 12 · search: limo")
        self.assertEqual(self.summary(0, 12, "x"), "No matches for “x”")


class SearchWiringTests(unittest.TestCase):
    """The small UI pieces that surround the field."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.app = load_headless_app(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_every_prefix_names_a_field_that_is_really_searched(self):
        fields = self.app.invoice_search_fields(
            {"customer": "Acme", "invoice_no": "1", "email": "a@b", "note": "n",
             "currency": "SEK", "amount": 1.0, "paid": 0.0, "due_date": "2026-11-01",
             "invoice_date": "", "p1_date": "", "p2_date": ""},
            "P1 att skapa",
        )
        for prefix, field in self.app.SEARCH_FIELD_PREFIXES.items():
            with self.subTest(prefix=prefix):
                self.assertIn(field, fields)

    def test_every_help_example_uses_a_real_prefix(self):
        for example in self.app.SEARCH_HELP_EXAMPLES:
            with self.subTest(example=example):
                terms = self.app.split_search_query(example)
                self.assertEqual(len(terms), 1)
                self.assertIsNotNone(terms[0][0], example)

    def test_the_clear_button_follows_the_field(self):
        class Button:
            def __init__(self):
                self.states = []

            def state(self, states):
                self.states.append(tuple(states))

        variable = SimpleNamespace(value="", get=lambda: variable.value, set=lambda value: setattr(variable, "value", value))
        button = Button()
        fake = SimpleNamespace(invoice_search_var=variable, clear_search_button=button, refresh=Mock())

        self.app.ReminderApp.on_invoice_search(fake)
        self.assertEqual(button.states[-1], ("disabled",))

        variable.value = "limo"
        self.app.ReminderApp.on_invoice_search(fake)
        self.assertEqual(button.states[-1], ("!disabled",))
        self.assertEqual(fake.refresh.call_count, 2)


class FakeTree:
    def __init__(self):
        self.rows = {}

    def get_children(self):
        return tuple(self.rows)

    def delete(self, item):
        self.rows.pop(item, None)

    def insert(self, _parent, _position, **options):
        self.rows[options["iid"]] = options["values"]


class FakeStatus:
    def __init__(self):
        self.text = ""

    def configure(self, **options):
        self.text = options.get("text", self.text)


class SearchInListViewTests(unittest.TestCase):
    """The real refresh, with a real database and a recording tree."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "search.sqlite3"
        self.app.init_db()
        self.addCleanup(self.temporary.cleanup)
        i18n.set_language("sv")
        self.addCleanup(i18n.set_language, "sv")

    def save(self, invoice_no, customer, *, amount=1000.0, paid=0.0, email="", note="", due="2026-11-01"):
        record = {
            "customer": customer, "invoice_no": invoice_no, "invoice_date": "2026-10-01",
            "due_date": due, "template_vendor": "", "amount": amount, "currency": "SEK",
            "paid": paid, "email": email, "source": "manual-entry",
            "source_hash": f"hash-{invoice_no}", "note": note, "reviewed": 1,
        }
        self.assertIsNone(self.app.save_invoice_record(record))

    def render(self, *, query="", filter_key="current"):
        tree = FakeTree()
        status = FakeStatus()
        fake = SimpleNamespace(
            tree=tree, current_filter_key=filter_key, show_detail=Mock(), search_status=status,
            invoice_search_var=SimpleNamespace(get=lambda: query),
            invoice_sort_column="due_date", invoice_sort_reverse=False,
        )
        self.app.ReminderApp.refresh(fake)
        return {values[0] for values in tree.rows.values()}, status.text

    def test_the_real_list_narrows_without_losing_rows(self):
        self.save("1001", "Limoeurope AB", amount=1500.0, email="anna@limoeurope.se", note="Avgift per påminnelse")
        self.save("1002", "Tadega AB", amount=300.0, due="2026-12-01")

        self.assertEqual(self.render()[0], {"1001", "1002"})
        self.assertEqual(self.render(query="limo")[0], {"1001"})
        self.assertEqual(self.render(query="belopp:1500")[0], {"1001"})
        self.assertEqual(self.render(query="not:avgift")[0], {"1001"})
        self.assertEqual(self.render(query="epost:tadega")[0], set())
        self.assertEqual(self.render(query="1001")[0], {"1001"})
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 2)

    def test_the_status_line_counts_the_matches(self):
        self.save("2001", "Limoeurope AB")
        self.save("2002", "Tadega AB")
        self.save("2003", "Limoeurope Syd")

        rows, status = self.render(query="limoeurope")
        self.assertEqual(rows, {"2001", "2003"})
        self.assertEqual(status, "Visar 2 av 3 · sökning: limoeurope")

        rows, status = self.render()
        self.assertEqual(status, "Visar 3 av 3")

    def test_a_hit_in_another_tab_is_reported_instead_of_hidden(self):
        self.save("3001", "Limoeurope AB", paid=1000.0)
        self.save("3002", "Tadega AB")

        rows, status = self.render(query="limoeurope", filter_key="current")
        self.assertEqual(rows, set())
        self.assertEqual(status, "Inga träffar i den här vyn · 1 träff i andra vyer")

        rows, status = self.render(query="limoeurope", filter_key="history")
        self.assertEqual(rows, {"3001"})
        self.assertEqual(status, "Visar 1 av 1 · sökning: limoeurope")

    def test_help_and_clear_are_real_actions(self):
        variable = SimpleNamespace(value="limo", get=lambda: variable.value, set=lambda value: setattr(variable, "value", value))
        focus = Mock()
        fake = SimpleNamespace(invoice_search_var=variable, invoice_search=focus, refresh=Mock())

        self.assertTrue(self.app.ReminderApp.clear_invoice_search(fake))
        self.assertEqual(variable.value, "")
        focus.focus_set.assert_called_once_with()
        self.assertFalse(self.app.ReminderApp.clear_invoice_search(fake))

        with patch.object(self.app.messagebox, "showinfo", create=True) as showinfo:
            self.app.ReminderApp.show_search_help(fake)
        self.assertEqual(showinfo.call_count, 1)
        body = showinfo.call_args.args[1]
        for example in self.app.SEARCH_HELP_EXAMPLES:
            self.assertIn(example, body)


if __name__ == "__main__":
    unittest.main()
