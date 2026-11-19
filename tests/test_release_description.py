"""The release page must describe the source archive, not a vanished ZIP.

The release carries the code at its tag: GitHub generates the archive itself,
so no file is uploaded and none can go stale. What *can* go stale is the text
on the page - GitHub keeps showing the release's original publication date while
the tag underneath moves - so the block is rewritten from the tag's commit and
everything outside the markers is kept exactly as it was written by hand.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))

import release_description as description  # noqa: E402


class PackageBlockTests(unittest.TestCase):
    def test_the_block_names_the_commit_and_the_date(self):
        block = description.package_block("0123456789abcdef", "v0.6.0", built="2026-11-19")
        self.assertIn("källkoden", block)
        self.assertIn("Uppdaterad: 2026-11-19", block)
        self.assertIn("`0123456`", block)
        self.assertIn("`v0.6.0`", block)
        self.assertTrue(block.startswith(description.OPENING))
        self.assertTrue(block.endswith(description.CLOSING))

    def test_the_block_points_at_the_source_code_download(self):
        block = description.package_block("abc1234", "v0.6.0", built="2026-11-19")
        self.assertIn("Source code (zip)", block)

    def test_the_date_defaults_to_today_in_utc(self):
        block = description.package_block("abc1234", "v0.6.0")
        self.assertIn(description.datetime.now(description.timezone.utc).date().isoformat(), block)

    def test_a_missing_commit_still_produces_a_usable_block(self):
        block = description.package_block("", "v0.6.0", built="2026-11-19")
        self.assertNotIn("Commit:", block)
        self.assertIn("v0.6.0", block)


class ReplaceBlockTests(unittest.TestCase):
    def block(self):
        return description.package_block("abc1234", "v0.6.0", built="2026-11-19")

    def test_a_new_description_gets_the_block_first(self):
        existing = "# PayPamin Flow 0.6.0\n\nHand-written notes.\n"
        result = description.replace_block(existing, self.block())
        self.assertTrue(result.startswith(description.OPENING))
        self.assertIn("Hand-written notes.", result)

    def test_an_existing_block_is_replaced_and_the_notes_are_kept(self):
        existing = (
            "Intro.\n\n<!-- release -->\nOLD\n<!-- /release -->\n\nOutro.\n"
        )
        result = description.replace_block(existing, self.block())
        self.assertNotIn("OLD", result)
        self.assertIn("Intro.", result)
        self.assertIn("Outro.", result)

    def test_a_refresh_does_not_stack_blocks(self):
        body = "Intro.\n"
        for _ in range(3):
            body = description.replace_block(body, self.block())
        self.assertEqual(body.count(description.OPENING), 1)
        self.assertEqual(body.count(description.CLOSING), 1)
        self.assertIn("Intro.", body)

    def test_the_previous_package_block_is_replaced(self):
        """An older page described a ZIP; that block must not survive."""
        existing = "Intro.\n\n<!-- paket -->\n- gammal zip\n<!-- /paket -->\n\nOutro.\n"
        result = description.replace_block(existing, self.block())
        self.assertIn(description.OPENING, result)
        self.assertIn("gammal zip", result, "unknown text outside our markers is never removed")

    def test_half_a_marker_never_deletes_the_notes(self):
        existing = "Notes that matter.\n<!-- release -->\nno closing marker\n"
        result = description.replace_block(existing, self.block())
        self.assertIn("Notes that matter.", result)
        self.assertIn("no closing marker", result)

    def test_an_empty_description_still_gets_a_block(self):
        self.assertTrue(description.replace_block("", self.block()).startswith(description.OPENING))
        self.assertTrue(description.replace_block(None, self.block()).startswith(description.OPENING))


if __name__ == "__main__":
    unittest.main()
