import json
import unittest
from urllib.error import HTTPError, URLError

from app_info import APP_LATEST_RELEASE_API, APP_RELEASES_URL
from i18n import set_language
from update_checker import (
    UpdateCheckError,
    canonical_version,
    fetch_latest_release,
    is_newer_version,
    version_key,
)


class FakeResponse:
    def __init__(self, payload):
        self.content = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def read(self, limit):
        return self.content[:limit]


def payload(tag="v0.6.0", url="https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.6.0", **values):
    result = {"tag_name": tag, "html_url": url, "draft": False, "prerelease": False}
    result.update(values)
    return result


class UpdateCheckerTests(unittest.TestCase):
    def tearDown(self):
        set_language("sv")

    def test_compares_versions_numerically(self):
        self.assertTrue(is_newer_version("v0.10.0", "0.9.9"))
        self.assertTrue(is_newer_version("0.5.1", "0.5.0"))
        self.assertFalse(is_newer_version("v0.5.0", "0.5.0"))
        self.assertFalse(is_newer_version("0.4.9", "0.5.0"))
        self.assertEqual(canonical_version(" v0.5.0 "), "0.5.0")

    def test_rejects_non_stable_version_format(self):
        with self.assertRaises(ValueError):
            version_key("0.5.0-beta")

    def test_fetches_latest_stable_release(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return FakeResponse(payload())

        release = fetch_latest_release(timeout=3, opener=opener)
        self.assertEqual(release.version, "0.6.0")
        self.assertEqual(release.tag_name, "v0.6.0")
        self.assertEqual(release.url, payload()["html_url"])
        self.assertEqual(calls[0][0].full_url, APP_LATEST_RELEASE_API)
        self.assertEqual(calls[0][1], 3)

    def test_uses_releases_page_when_release_url_is_empty(self):
        release = fetch_latest_release(opener=lambda request, timeout: FakeResponse(payload(url="")))
        self.assertEqual(release.url, APP_RELEASES_URL)

    def test_rejects_untrusted_release_url(self):
        with self.assertRaises(UpdateCheckError):
            fetch_latest_release(opener=lambda request, timeout: FakeResponse(payload(url="http://example.com/update")))

    def test_rejects_prerelease_response(self):
        with self.assertRaises(UpdateCheckError):
            fetch_latest_release(opener=lambda request, timeout: FakeResponse(payload(prerelease=True)))

    def test_missing_release_has_translated_error(self):
        set_language("en")

        def opener(request, timeout):
            raise HTTPError(request.full_url, 404, "Not Found", None, None)

        with self.assertRaisesRegex(UpdateCheckError, "No published stable release"):
            fetch_latest_release(opener=opener)

    def test_network_failure_has_translated_error(self):
        set_language("en")

        def opener(request, timeout):
            raise URLError("offline")

        with self.assertRaisesRegex(UpdateCheckError, "Could not contact GitHub"):
            fetch_latest_release(opener=opener)

    def test_rate_limit_has_specific_error(self):
        def opener(request, timeout):
            raise HTTPError(request.full_url, 429, "Too Many Requests", None, None)

        with self.assertRaisesRegex(UpdateCheckError, "Försök igen senare"):
            fetch_latest_release(opener=opener)


if __name__ == "__main__":
    unittest.main()
