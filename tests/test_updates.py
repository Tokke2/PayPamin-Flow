import hashlib
import json
import unittest
from urllib.error import HTTPError, URLError

from app_info import (
    APP_LATEST_RELEASE_API,
    APP_NAME,
    APP_RELEASES_URL,
    PYTHON_PACKAGE_REQUIRED_FILES,
    PYTHON_RELEASE_ASSET,
    PYTHON_RELEASE_MANIFEST,
    fingerprint_package_files,
)
from i18n import set_language
from update_checker import (
    UPDATE_CHECK_INTERVAL_MS,
    ReleaseAsset,
    ReleaseInfo,
    UpdateCheckError,
    canonical_version,
    fetch_latest_release,
    is_newer_version,
    is_update_available,
    missing_release_assets,
    update_change_kind,
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
    result = {"id": 100, "tag_name": tag, "html_url": url, "draft": False, "prerelease": False}
    result.update(values)
    return result


def build_manifest(commit="a" * 40):
    files = {
        name: hashlib.sha256(name.encode("utf-8")).hexdigest()
        for name in PYTHON_PACKAGE_REQUIRED_FILES
        if name != "build_info.py"
    }
    return {
        "format": 1,
        "application": APP_NAME,
        "version": "0.6.0",
        "release_id": "100",
        "commit": commit,
        "package_fingerprint": fingerprint_package_files(files),
        "files": files,
    }


class UpdateCheckerTests(unittest.TestCase):
    def tearDown(self):
        set_language("sv")

    def test_compares_versions_numerically(self):
        self.assertTrue(is_newer_version("v0.10.0", "0.9.9"))
        self.assertTrue(is_newer_version("0.5.1", "0.5.0"))
        self.assertFalse(is_newer_version("v0.5.0", "0.5.0"))
        self.assertFalse(is_newer_version("0.4.9", "0.5.0"))
        self.assertEqual(canonical_version(" v0.5.0 "), "0.5.0")

    def test_same_version_release_builds_use_release_identity(self):
        release = ReleaseInfo("0.6.0", "v0.6.0", "https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.6.0", release_id="200")
        self.assertTrue(is_update_available(release, "0.6.0", "100"))
        self.assertFalse(is_update_available(release, "0.6.0", "200"))
        self.assertFalse(is_update_available(release, "0.6.0", ""))
        self.assertTrue(is_update_available(release, "0.5.9", "100"))
        self.assertFalse(is_update_available(release, "0.6.1", "100"))

    def test_same_version_compares_commit_and_files_before_release_id(self):
        release = ReleaseInfo(
            "0.6.0",
            "v0.6.0",
            "https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.6.0",
            release_id="200",
            release_commit="b" * 40,
            package_fingerprint="b" * 64,
        )
        current = {
            "current_release_id": "100",
            "current_release_commit": "a" * 40,
            "current_package_fingerprint": "a" * 64,
        }
        self.assertTrue(is_update_available(release, "0.6.0", **current))
        self.assertTrue(is_update_available(release, "0.6.0", **{**current, "current_release_commit": "b" * 40}))
        self.assertFalse(is_update_available(release, "0.6.0", **{
            **current,
            "current_release_commit": "b" * 40,
            "current_package_fingerprint": "b" * 64,
        }))
        without_manifest = ReleaseInfo(
            "0.6.0", "v0.6.0", release.url, release_id="200"
        )
        self.assertFalse(is_update_available(without_manifest, "0.6.0", **current))

    def test_release_assets_must_be_complete_before_install(self):
        url = "https://github.com/Tokke2/PayPamin-Flow/releases/download/v0.6.0/"
        package = ReleaseAsset(PYTHON_RELEASE_ASSET, url + PYTHON_RELEASE_ASSET)
        checksum = ReleaseAsset(PYTHON_RELEASE_ASSET + ".sha256", url + PYTHON_RELEASE_ASSET + ".sha256")
        release = ReleaseInfo("0.6.0", "v0.6.0", "https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.6.0", assets=(package,))
        self.assertEqual(missing_release_assets(release), (PYTHON_RELEASE_ASSET + ".sha256",))
        release = ReleaseInfo("0.6.0", "v0.6.0", release.url, assets=(package, checksum))
        self.assertEqual(missing_release_assets(release), ())

    def test_update_change_kind_distinguishes_version_commit_and_files(self):
        release = ReleaseInfo(
            "0.6.0", "v0.6.0", "https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.6.0",
            release_commit="b" * 40, package_fingerprint="b" * 64,
        )
        self.assertEqual(update_change_kind(release, "0.6.0", "a" * 40, "a" * 64), "commit_and_files")
        self.assertEqual(update_change_kind(release, "0.6.0", "a" * 40, "b" * 64), "commit")
        self.assertEqual(update_change_kind(release, "0.6.0", "b" * 40, "a" * 64), "files")
        self.assertEqual(update_change_kind(release, "0.6.0", "", ""), "release")
        newer = ReleaseInfo("0.7.0", "v0.7.0", release.url)
        self.assertEqual(update_change_kind(newer), "version")

    def test_release_identity_is_optional_for_newer_versions(self):
        new_version = ReleaseInfo("0.6.1", "v0.6.1", "https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.6.1")
        same_version = ReleaseInfo("0.6.0", "v0.6.0", "https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.6.0")
        self.assertTrue(is_update_available(new_version, "0.6.0", "100"))
        self.assertFalse(is_update_available(same_version, "0.6.0", "100"))

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
        self.assertEqual(release.release_id, "100")
        self.assertEqual(release.url, payload()["html_url"])
        self.assertEqual(calls[0][0].full_url, APP_LATEST_RELEASE_API)
        self.assertEqual(calls[0][1], 3)

    def test_fetches_commit_and_per_file_manifest(self):
        commit = "a" * 40
        manifest = build_manifest(commit)
        manifest_url = f"https://github.com/Tokke2/PayPamin-Flow/releases/download/v0.6.0/{PYTHON_RELEASE_MANIFEST}"
        responses = {
            APP_LATEST_RELEASE_API: payload(
                target_commitish=commit,
                assets=[{"name": PYTHON_RELEASE_MANIFEST, "browser_download_url": manifest_url}],
            ),
            manifest_url: manifest,
        }
        calls = []

        def opener(request, timeout):
            calls.append(request.full_url)
            return FakeResponse(responses[request.full_url])

        release = fetch_latest_release(opener=opener)
        self.assertEqual(release.release_commit, commit)
        self.assertEqual(release.package_fingerprint, manifest["package_fingerprint"])
        self.assertEqual(calls, [APP_LATEST_RELEASE_API, manifest_url])

    def test_rejects_manifest_whose_file_fingerprint_is_wrong(self):
        commit = "a" * 40
        manifest = build_manifest(commit)
        manifest["package_fingerprint"] = "0" * 64
        manifest_url = f"https://github.com/Tokke2/PayPamin-Flow/releases/download/v0.6.0/{PYTHON_RELEASE_MANIFEST}"
        responses = {
            APP_LATEST_RELEASE_API: payload(
                target_commitish=commit,
                assets=[{"name": PYTHON_RELEASE_MANIFEST, "browser_download_url": manifest_url}],
            ),
            manifest_url: manifest,
        }
        with self.assertRaisesRegex(UpdateCheckError, "byggmanifest"):
            fetch_latest_release(opener=lambda request, timeout: FakeResponse(responses[request.full_url]))

    def test_uses_releases_page_when_release_url_is_empty(self):
        release = fetch_latest_release(opener=lambda request, timeout: FakeResponse(payload(url="")))
        self.assertEqual(release.url, APP_RELEASES_URL)

    def test_rejects_untrusted_release_url(self):
        with self.assertRaises(UpdateCheckError):
            fetch_latest_release(opener=lambda request, timeout: FakeResponse(payload(url="http://example.com/update")))

    def test_rejects_branch_name_as_release_identity(self):
        with self.assertRaises(UpdateCheckError):
            fetch_latest_release(opener=lambda request, timeout: FakeResponse(payload(id="main")))

    def test_rejects_prerelease_response(self):
        with self.assertRaises(UpdateCheckError):
            fetch_latest_release(opener=lambda request, timeout: FakeResponse(payload(prerelease=True)))

    def test_release_assets_are_read(self):
        assets = [
            {"name": "PayPamin-Flow-Linux.tar.gz", "browser_download_url": "https://github.com/Tokke2/PayPamin-Flow/releases/download/v0.6.0/PayPamin-Flow-Linux.tar.gz"},
            {"name": "PayPamin-Flow-Linux.tar.gz.sha256", "browser_download_url": "https://github.com/Tokke2/PayPamin-Flow/releases/download/v0.6.0/PayPamin-Flow-Linux.tar.gz.sha256"},
        ]
        release = fetch_latest_release(opener=lambda request, timeout: FakeResponse(payload(assets=assets)))
        self.assertEqual([asset.name for asset in release.assets], [asset["name"] for asset in assets])

    def test_automatic_checks_run_twice_per_day(self):
        self.assertEqual(UPDATE_CHECK_INTERVAL_MS, 12 * 60 * 60 * 1000)

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
