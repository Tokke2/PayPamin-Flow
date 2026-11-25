"""Guard rails for the CI workflow used to verify every change.

The automated session branch must be verifiable without a pull request:
Arena tracks the working branch through its pull request, so closing a
temporary CI pull request closes the branch itself and stops the session.
These tests fail if the workflow trigger or the documented rule is removed.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"


def _push_trigger_block(text):
    """Return the indented body of the workflow's ``push:`` trigger."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "push:":
            continue
        indent = len(line) - len(line.lstrip())
        body = []
        for following in lines[index + 1:]:
            if not following.strip():
                body.append(following)
                continue
            if len(following) - len(following.lstrip()) <= indent:
                break
            body.append(following)
        return "\n".join(body)
    return ""


class WorkflowGuardTests(unittest.TestCase):
    """Skipped in the release package, which ships no ``.github`` folder."""

    def setUp(self):
        if not WORKFLOW.exists():
            self.skipTest("workflow file is not part of the release package")
        if not CONTRIBUTING.exists():
            self.skipTest("CONTRIBUTING.md is not part of the release package")
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_session_branches_are_tested_on_push_not_only_in_pull_requests(self):
        block = _push_trigger_block(self.workflow)
        self.assertTrue(block, "build.yml has no push trigger")
        self.assertIn("arena/**", block)
        branches_line = next(
            (line for line in block.splitlines() if line.strip().startswith("branches:")),
            "",
        )
        self.assertNotIn("main", branches_line)

    def test_agents_md_documents_all_hard_rules(self):
        agents = ROOT / "AGENTS.md"
        self.assertTrue(agents.is_file(), "AGENTS.md must exist in repository root")
        text = agents.read_text(encoding="utf-8")
        for required in ("Latest", "main", "merge", "quiet_faults.report_fault", "errors.log", "7 dagar", "10"):
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_release_refresh_marks_release_as_latest(self):
        refresh = self.workflow.split("refresh-release-files:", 1)[1]
        self.assertIn("make_latest=true", refresh)
        self.assertIn("draft=false", refresh)
        self.assertIn("prerelease=false", refresh)

    def test_pull_requests_still_run_the_same_matrix(self):
        self.assertIn("pull_request:", self.workflow)

    def test_the_release_publishes_backward_compatible_python_package(self):
        """Both the tag archive and PayPamin-Flow-Python.zip + .sha256 must ship."""
        self.assertIn("types: [published]", self.workflow)
        self.assertNotIn("publish-python-package:", self.workflow)
        refresh = self.workflow.split("refresh-release-files:", 1)[1]
        self.assertIn("packaging/package_release.py", refresh)
        self.assertIn("PayPamin-Flow-Python.zip", refresh)
        self.assertIn("PayPamin-Flow-Python.zip.sha256", refresh)
        self.assertIn("gh release upload", refresh)

    def test_permissions_stay_read_only_at_the_top_level(self):
        self.assertIn("permissions:\n  contents: read\n", self.workflow)

    def test_contributing_documents_the_no_temporary_pull_request_rule(self):
        text = CONTRIBUTING.read_text(encoding="utf-8")
        self.assertIn("pull request", text.lower())
        self.assertTrue(
            "arena" in text.lower() or "session branch" in text.lower(),
            "CONTRIBUTING.md must explain the session-branch CI rule",
        )

    def test_branding_is_verified_from_the_vector_masters(self):
        self.assertIn("python assets/verify_branding.py", self.workflow)
        self.assertTrue((ROOT / "assets" / "verify_branding.py").is_file())

    def test_ci_never_uses_cross_job_artifact_actions(self):
        """Release assets are built directly in refresh-release-files without artifact hops."""
        self.assertNotIn("upload-artifact", self.workflow)
        self.assertNotIn("download-artifact", self.workflow)

    def test_a_push_to_the_working_branch_moves_the_tag(self):
        """Moving the tag is what makes the release carry the newest code."""
        block = self.workflow.split("refresh-release-files:", 1)
        self.assertEqual(len(block), 2, "build.yml has no release refresh job")
        refresh = block[1]
        self.assertIn("github.event_name == 'push'", refresh)
        self.assertIn("startsWith(github.ref, 'refs/heads/arena/')", refresh)
        self.assertIn("git/refs/tags/$tag", refresh)
        # The page is rewritten from the commit the tag now points at.
        self.assertIn("packaging/release_description.py", refresh)
        self.assertIn("releases/$release_id", refresh)

    def test_the_release_is_never_refreshed_from_main(self):
        """The work lives on the branch, so main is not a publish source.

        A refresh from main would put code in the release that no branch
        contains and that the session's own branch would then report as an
        update in the wrong direction.
        """
        refresh = self.workflow.split("refresh-release-files:", 1)[1]
        requirement = re.search(r"^    if: .*$", refresh, re.MULTILINE)
        self.assertIsNotNone(requirement)
        self.assertNotIn("refs/heads/main", requirement.group(0))

    def test_the_workflow_never_merges_or_opens_a_pull_request(self):
        """Merging is the owner's decision and is never automated."""
        lowered = self.workflow.lower()
        for forbidden in ("gh pr merge", "gh pr create", "pulls", "merge --", "git merge"):
            with self.subTest(command=forbidden):
                self.assertNotIn(forbidden, lowered)

    def test_the_release_job_verifies_its_own_result(self):
        """Moving a tag is a request; only reading it back proves it happened."""
        refresh = self.workflow.split("refresh-release-files:", 1)[1]
        self.assertIn("packaging/verify_release.py", refresh)
        self.assertIn("--commit \"$COMMIT\"", refresh)
        # The check must come after the tag move, not before it.
        self.assertLess(
            refresh.index("git/refs/tags/$tag"),
            refresh.index("packaging/verify_release.py"),
            "the release must be verified after the tag has been moved",
        )

    def test_the_verification_step_skips_a_repository_without_a_release(self):
        refresh = self.workflow.split("refresh-release-files:", 1)[1]
        verify = refresh.split("Verify the release really carries this commit", 1)[1]
        self.assertIn("releases/tags/$tag", verify)
        self.assertIn("nothing to verify", verify)

    def test_the_verification_is_the_last_word_of_the_job(self):
        refresh = self.workflow.split("refresh-release-files:", 1)[1]
        steps = [line.strip() for line in refresh.splitlines() if line.strip().startswith("- name:")]
        self.assertTrue(steps[-1].startswith("- name: Verify the release"), steps)

    def test_the_verification_script_is_shipped_with_its_own_tests(self):
        self.assertTrue((ROOT / "packaging" / "verify_release.py").is_file())
        self.assertTrue((ROOT / "tests" / "test_verify_release.py").is_file())

    def test_the_desktop_job_runs_the_suite_on_every_push(self):
        self.assertIn("unittest discover -s tests", self.workflow)
        self.assertIn("python assets/verify_branding.py", self.workflow)


if __name__ == "__main__":
    unittest.main()
