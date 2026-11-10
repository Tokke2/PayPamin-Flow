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
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_session_branches_are_tested_on_push_not_only_in_pull_requests(self):
        block = _push_trigger_block(self.workflow)
        self.assertTrue(block, "build.yml has no push trigger")
        self.assertIn("arena/**", block)

    def test_pull_requests_still_run_the_same_matrix(self):
        self.assertIn("pull_request:", self.workflow)

    def test_release_workflow_keeps_its_publish_job(self):
        self.assertIn("types: [published]", self.workflow)
        self.assertIn("publish-python-package:", self.workflow)

    def test_permissions_stay_read_only_at_the_top_level(self):
        self.assertIn("permissions:\n  contents: read\n", self.workflow)

    def test_contributing_documents_the_no_temporary_pull_request_rule(self):
        text = CONTRIBUTING.read_text(encoding="utf-8")
        self.assertIn("pull request", text.lower())
        self.assertTrue(
            "arena" in text.lower() or "session branch" in text.lower(),
            "CONTRIBUTING.md must explain the session-branch CI rule",
        )

    def test_workflow_only_publishes_for_releases(self):
        publish_block = self.workflow.split("publish-python-package:", 1)[1]
        requirement = re.search(r"^    if: .*$", publish_block, re.MULTILINE)
        self.assertIsNotNone(requirement)
        self.assertIn("github.event_name == 'release'", requirement.group(0))


if __name__ == "__main__":
    unittest.main()
