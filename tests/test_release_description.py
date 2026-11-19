"""The release page must describe the package that is actually uploaded.

While the application stays at 0.6.0 the release is rebuilt in place on every
branch push, so a description that still shows last week's checksum and file
count is indistinguishable from a release that was never refreshed. These tests
pin the two properties that keep the page honest: the numbers come from the ZIP
itself, and nothing outside the delimited block is ever rewritten.
"""
import hashlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))

import release_description as description  # noqa: E402


def make_package(folder: Path, names=("a.py", "b.py"), payload=b"print(1)\n") -> Path:
    archive = folder / "PayPamin-Flow-Python.zip"
    with zipfile.ZipFile(archive, "w") as package:
        for name in names:
            package.writestr(name, payload)
    return archive


class ArchiveFactsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def test_facts_describe_the_real_zip(self):
        archive = make_package(self.folder, names=("a.py", "b.py", "c.py"))
        facts = description.archive_facts(archive)
        self.assertEqual(facts["name"], "PayPamin-Flow-Python.zip")
        self.assertEqual(facts["entries"], 3)
        self.assertEqual(facts["size"], archive.stat().st_size)
        self.assertEqual(facts["sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())

    def test_directory_entries_are_not_counted_as_files(self):
        archive = self.folder / "PayPamin-Flow-Python.zip"
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("assets/", b"")
            package.writestr("assets/logo.png", b"png")
        self.assertEqual(description.archive_facts(archive)["entries"], 1)

    def test_a_stale_sidecar_is_reported_instead_of_published(self):
        archive = make_package(self.folder)
        sidecar = archive.with_suffix(archive.suffix + ".sha256")
        sidecar.write_text("0" * 64 + "  PayPamin-Flow-Python.zip\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as caught:
            description.archive_facts(archive)
        self.assertIn("describes", str(caught.exception))

    def test_a_matching_sidecar_is_accepted(self):
        archive = make_package(self.folder)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        sidecar = archive.with_suffix(archive.suffix + ".sha256")
        sidecar.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
        self.assertEqual(description.archive_facts(archive)["sha256"], digest)


class PackageBlockTests(unittest.TestCase):
    def facts(self, **overrides):
        facts = {"name": "PayPamin-Flow-Python.zip", "entries": 134, "size": 1024 * 1024, "sha256": "a" * 64}
        facts.update(overrides)
        return facts

    def test_the_block_names_the_package_count_size_and_checksum(self):
        block = description.package_block(self.facts(), "0123456789abcdef")
        self.assertIn("`PayPamin-Flow-Python.zip`", block)
        self.assertIn("134 filer", block)
        self.assertIn("1024 kB", block)
        self.assertIn("a" * 64, block)
        self.assertIn("0123456", block)
        self.assertTrue(block.startswith(description.OPENING))
        self.assertTrue(block.endswith(description.CLOSING))

    def test_the_block_survives_a_missing_commit(self):
        block = description.package_block(self.facts(), "")
        self.assertNotIn("byggt av `", block)

    def test_the_two_files_are_described_as_the_whole_release(self):
        block = description.package_block(self.facts(), "abc1234")
        self.assertIn("exakt dessa två filer", block)


class ReplaceBlockTests(unittest.TestCase):
    def facts(self):
        return {"name": "PayPamin-Flow-Python.zip", "entries": 134, "size": 1024 * 1024, "sha256": "a" * 64}

    def test_a_new_description_gets_the_block_first(self):
        existing = "# PayPamin Flow 0.6.0\n\nHand-written notes.\n"
        result = description.replace_block(existing, "BLOCK")
        self.assertTrue(result.startswith("BLOCK"))
        self.assertIn("Hand-written notes.", result)

    def test_an_existing_block_is_replaced_and_the_notes_are_kept(self):
        existing = "Intro.\n\n<!-- paket -->\nOLD\n<!-- /paket -->\n\nOutro.\n"
        result = description.replace_block(existing, "NEW")
        self.assertIn("NEW", result)
        self.assertNotIn("OLD", result)
        self.assertIn("Intro.", result)
        self.assertIn("Outro.", result)

    def test_a_refresh_does_not_stack_blocks(self):
        block = description.package_block(self.facts(), "abc1234")
        body = "Intro.\n"
        for _ in range(3):
            body = description.replace_block(body, block)
        self.assertEqual(body.count(description.OPENING), 1)
        self.assertEqual(body.count(description.CLOSING), 1)
        self.assertIn("Intro.", body)

    def test_half_a_marker_never_deletes_the_notes(self):
        existing = "Notes that matter.\n<!-- paket -->\nno closing marker\n"
        result = description.replace_block(existing, "BLOCK")
        self.assertIn("Notes that matter.", result)
        self.assertIn("no closing marker", result)

    def test_an_empty_description_still_gets_a_block(self):
        self.assertTrue(description.replace_block("", "BLOCK").startswith("BLOCK"))
        self.assertTrue(description.replace_block(None, "BLOCK").startswith("BLOCK"))


if __name__ == "__main__":
    unittest.main()
