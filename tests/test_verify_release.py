"""The release job must check its own result, not just its exit status.

Asking GitHub to move a tag proves nothing about whether it did. A rejected tag
move, a page that kept an older body, a leftover upload or a stale archive all
leave a release that looks fine to the job and wrong to the app. These tests fake
GitHub's answers and the archive so every one of those cases has to be caught,
and so a slow codeload gets a retry instead of a false alarm.
"""
import io
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))

import verify_release as verification  # noqa: E402

COMMIT = "cef8317e515dd32845ec8315f7ff0916aa583a91"
OTHER = "b2f6ac4aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
TAG = "v0.6.0"
REPOSITORY = "Tokke2/PayPamin-Flow"


def make_archive(files, root="PayPamin-Flow-0.6.0"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(f"{root}/{name}" if root else name, content)
    return buffer.getvalue()


FILES = {
    "app_info.py": "APP_VERSION = \"0.6.0\"\n",
    "paypamin_flow.py": "print('hej')\n",
    "tests/test_smoke.py": "pass\n",
}


class ReleaseVerificationTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.checkout = Path(self.folder.name)
        for name, content in FILES.items():
            target = self.checkout / name
            target.parent.mkdir(parents=True, exist_ok=True)
            # Bytes, not text: on Windows text mode would write CRLF and the
            # fixture would differ from the archive for the wrong reason.
            target.write_bytes(content.encode("utf-8"))
        self.payload = make_archive(FILES)

    def api(self, *, tag_commit=COMMIT, body=None, assets=None, tag_type="commit"):
        body = f"<!-- release -->\n- Commit: `{COMMIT[:7]}`\n" if body is None else body
        target = tag_commit
        answers = {}
        if tag_type == "tag":
            # An annotated tag points at a tag object, which points at a commit.
            answers[f"git/ref/tags/{TAG}"] = {"object": {"sha": "d" * 40, "type": "tag"}}
            answers[f"git/tags/{'d' * 40}"] = {"object": {"sha": COMMIT, "type": "commit"}}
        else:
            answers[f"git/ref/tags/{TAG}"] = {"object": {"sha": target, "type": "commit"}}
        answers[f"releases/tags/{TAG}"] = {"id": 444043893, "body": body, "assets": assets or []}

        def read(repository, path):
            if path not in answers:
                raise verification.ReleaseVerificationError("404")
            return answers[path]

        return read

    def verify(self, *, fetch=None, api=None, commit=COMMIT, **kwargs):
        return verification.verify(
            tag=TAG,
            repository=REPOSITORY,
            commit=commit,
            checkout=self.checkout,
            api=api or self.api(),
            fetch=fetch or (lambda url: self.payload),
            sleep=lambda _seconds: None,
            **kwargs,
        )

    def test_a_release_that_matches_the_commit_has_no_problems(self):
        self.assertEqual(self.verify(), [])

    def test_a_tag_that_points_elsewhere_is_a_problem(self):
        problems = self.verify(api=self.api(tag_commit=OTHER))
        self.assertEqual(len(problems), 1)
        self.assertIn("pekar på", problems[0])
        self.assertIn(OTHER[:7], problems[0])

    def test_an_annotated_tag_is_followed_to_its_commit(self):
        self.assertEqual(self.verify(api=self.api(tag_type="tag")), [])

    def test_a_page_that_names_another_commit_is_a_problem(self):
        problems = self.verify(api=self.api(body="- Commit: `1111111`\n"))
        self.assertTrue(any("nämner inte commit" in problem for problem in problems))

    def test_an_uploaded_file_means_the_release_is_not_the_source_code(self):
        problems = self.verify(api=self.api(assets=[{"name": "PayPamin-Flow-Python.zip"}]))
        self.assertTrue(any("uppladdade fil" in problem for problem in problems))
        self.assertIn("PayPamin-Flow-Python.zip", " ".join(problems))

    def test_a_missing_release_is_reported(self):
        def read(repository, path):
            raise verification.ReleaseVerificationError("404 Not Found")

        problems = self.verify(api=read)
        self.assertTrue(any("gick inte att läsa" in problem for problem in problems))
        self.assertTrue(any("Releasen för" in problem for problem in problems))

    def test_an_archive_that_differs_from_the_commit_is_a_problem(self):
        payload = make_archive({**FILES, "paypamin_flow.py": "print('annan kod')\n"})
        problems = self.verify(fetch=lambda url: payload)
        self.assertTrue(any("skiljer sig" in problem for problem in problems))
        self.assertIn("paypamin_flow.py", " ".join(problems))

    def test_a_crlf_checkout_is_not_a_difference(self):
        """A Windows working tree with core.autocrlf has CRLF; the commit has LF."""
        (self.checkout / "paypamin_flow.py").write_bytes(b"print('hej')\r\n")
        self.assertEqual(self.verify(), [])

    def test_a_file_committed_with_crlf_still_has_to_match(self):
        """The .bat and .vbs starters are committed with CRLF on purpose."""
        payload = make_archive({**FILES, "start.bat": "@echo off\r\n"})
        (self.checkout / "start.bat").write_bytes(b"@echo off \r\n")
        problems = self.verify(fetch=lambda url: payload)
        self.assertTrue(any("start.bat" in problem for problem in problems))

    def test_an_archive_with_another_root_folder_is_a_problem(self):
        problems = self.verify(fetch=lambda url: make_archive(FILES, root="annat-namn"))
        self.assertTrue(any("rotmappen" in problem for problem in problems))

    def test_an_archive_without_the_application_is_a_problem(self):
        problems = self.verify(fetch=lambda url: make_archive({"README.md": "x"}))
        self.assertTrue(any("saknar" in problem for problem in problems))

    def test_a_damaged_archive_is_a_problem_not_a_crash(self):
        problems = self.verify(fetch=lambda url: b"not a zip")
        self.assertTrue(any("skadat" in problem for problem in problems))

    def test_a_stale_archive_is_retried_before_the_job_fails(self):
        """GitHub regenerates an archive a moment after the tag moves."""
        calls = []

        def fetch(url):
            calls.append(url)
            if len(calls) < 3:
                raise HTTPError(url, 503, "not ready", None, None)
            return self.payload

        self.assertEqual(self.verify(fetch=fetch), [])
        self.assertEqual(len(calls), 3)

    def test_an_archive_that_never_arrives_is_reported_with_the_reason(self):
        def fetch(url):
            raise URLError("timed out")

        problems = self.verify(fetch=fetch, attempts=3)
        self.assertTrue(any("gick inte att hämta" in problem for problem in problems))
        self.assertIn("timed out", " ".join(problems))

    def test_an_empty_commit_is_refused_before_any_request(self):
        def boom(*_args, **_kwargs):
            raise AssertionError("no request should be made without a commit")

        problems = self.verify(api=boom, fetch=boom, commit="")
        self.assertEqual(len(problems), 1)
        self.assertIn("Ingen commit", problems[0])


class CommandLineTests(unittest.TestCase):
    def run_main(self, problems):
        with mock.patch.object(verification, "verify", return_value=problems) as patched:
            code = verification.main(
                ["--tag", TAG, "--repository", REPOSITORY, "--commit", COMMIT]
            )
        self.assertTrue(patched.called)
        self.assertEqual(patched.call_args.kwargs["tag"], TAG)
        self.assertEqual(patched.call_args.kwargs["commit"], COMMIT)
        return code

    def test_a_verified_release_exits_zero(self):
        with mock.patch("builtins.print"):
            self.assertEqual(self.run_main([]), 0)

    def test_a_problem_exits_non_zero_and_is_an_annotation(self):
        with mock.patch("builtins.print") as printed:
            self.assertEqual(self.run_main(["Taggen pekar fel"]), 1)
        self.assertEqual(printed.call_args.args[0], "::error::Taggen pekar fel")

    def test_every_problem_is_printed(self):
        with mock.patch("builtins.print") as printed:
            self.run_main(["ett", "två"])
        self.assertEqual(printed.call_count, 2)


if __name__ == "__main__":
    unittest.main()
