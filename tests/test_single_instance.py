import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

from single_instance import SingleInstance


class SingleInstanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.instances = []

    def instance(self, callback=None):
        instance = SingleInstance(self.directory, callback or Mock())
        self.instances.append(instance)
        return instance

    def tearDown(self):
        for instance in reversed(self.instances):
            instance.release()

    def test_second_start_activates_existing_instance_without_owning_lock(self):
        activated = threading.Event()
        first = self.instance(activated.set)
        second = self.instance()

        self.assertTrue(first.acquire(timeout=0.5))
        self.assertFalse(second.acquire(timeout=2.0))

        self.assertTrue(second.activated_existing)
        self.assertFalse(second.owned)
        self.assertTrue(activated.wait(1.0))
        self.assertEqual(first.owner_pid(), os.getpid())

    def test_release_allows_a_later_start_to_become_owner(self):
        first = self.instance()
        second = self.instance()

        self.assertTrue(first.acquire(timeout=0.5))
        self.assertTrue((self.directory / "instance.json").is_file())
        first.release()
        self.assertFalse((self.directory / "instance.json").exists())

        self.assertTrue(second.acquire(timeout=0.5))
        self.assertTrue(second.owned)

    def test_invalid_activation_token_is_not_accepted(self):
        activated = threading.Event()
        first = self.instance(activated.set)
        self.assertTrue(first.acquire(timeout=0.5))
        state_path = self.directory / "instance.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["token"] = "invalid-token-that-does-not-match-the-owner"
        state_path.write_text(json.dumps(state), encoding="utf-8")

        second = self.instance()
        self.assertFalse(second.activate_existing())
        self.assertFalse(activated.wait(0.2))

    def test_activation_server_is_loopback_only(self):
        first = self.instance()
        self.assertTrue(first.acquire(timeout=0.5))
        self.assertEqual(first._server.getsockname()[0], "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
