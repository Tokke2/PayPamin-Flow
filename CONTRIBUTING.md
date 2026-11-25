# Contributing

Thanks for considering a contribution to PayPamin Flow. See [`AGENTS.md`](AGENTS.md) for the complete set of hard repository rules (`- hård regel`).

1. Open an issue describing the change, using synthetic or anonymized examples only.
2. Do not commit customer invoices, generated reminders, local databases, logs, or company logos unless you have permission and intend to publish them.
3. Run the tests before opening a pull request:

   ```sh
   python -m unittest discover -s tests -v
   ```

4. Keep invoice parsing changes covered by synthetic text fixtures. Never use real customer information in tests.
5. For UI or startup changes, check Windows, macOS and Linux behavior. Keep the product name, creator attribution and shared icon consistent by using `app_info.py` and `assets/`.
6. Wrap every user-visible Swedish message key with `_()` from `i18n.py` and add its English translation. Keep dynamic values in named placeholders and run the translation completeness tests. Both the UI and generated documents must work in Swedish and English.
7. Keep currency on the invoice, preserve SEK as the backward-compatible default and never introduce implicit currency conversion. Cover formatting, parser suggestions and database migrations with synthetic tests.
8. Keep the release tag, the updater and `build_info.py` consistent: the release is the source archive at the tag, so the updater compares the tag's commit with `APP_RELEASE_COMMIT` and never relies on an uploaded file. Test updates with synthetic archives; never run replacement helpers against a real development or production installation.
9. **The release is the source code at its tag, published exclusively from the single active working branch and always marked `Latest`.** Only one working branch is kept on GitHub (`main` is never used and branches are never merged). Every push to `arena/**` moves the tag to that commit once the tests pass, rewrites the release page's block with the new commit, and marks the release as `Latest` (`make_latest=true`, `draft=false`, `prerelease=false`). GitHub generates the archive itself, so nothing is uploaded and the download link can never disagree with the code. Nothing merges, `main` is never a publish source, and no pull request is opened from a session branch (see point 10). The job then reads the result back with `packaging/verify_release.py` - tag, `Latest` status, page, file list and the archive itself - because a step that only reports its own exit status cannot tell whether the move was accepted. `tests/test_ci_workflow.py` keeps all of that in place.
10. **Never open a pull request from an `arena/*` session branch.** Arena tracks the working branch through its pull request, so a temporary PR opened only to trigger CI closes the branch when the PR is closed. CI already runs the full Windows/macOS/Linux matrix on every push to `arena/**` (see `.github/workflows/build.yml`), so push and read the workflow run instead. `tests/test_ci_workflow.py` keeps that trigger in place.
11. **Never swallow an exception silently.** `except ...: pass` fails the suite (`tests/test_quiet.py`). Call `quiet_faults.report_fault()` instead: expected teardown is then one warning in `app.log`, anything unexpected is an error with a traceback and reaches `errors.log`. Repeats are counted, not reprinted, so a callback that runs on every repaint stays readable.

PayPamin Flow is created by Rickard Längkvist. Copyright © 2026 Rickard Längkvist.
