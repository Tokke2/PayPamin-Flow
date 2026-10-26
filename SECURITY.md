# Security and sensitive data

PayPamin Flow processes invoice PDFs and customer data. Do not attach real invoices, exported reminders, the local SQLite database, or unredacted logs to public GitHub issues or pull requests.

For a bug report, use synthetic or thoroughly anonymized examples. The app is a prototype; review each extracted field and generated reminder before use. Report security concerns privately to the repository maintainer rather than opening a public issue.

Autostart entries are created only for the current OS user and can be disabled in Settings. They launch the same local application and do not add a network service.

## Automatic updates

Automatic updates retrieve only stable releases from the project's GitHub repository over HTTPS. Native packages must include a matching SHA-256 file, and the package is verified before extraction. Archive paths are restricted to the update workspace. No invoice, customer or settings data is included in update requests or packages.

Only the native application installation is replaced; local business data is not part of the update. A temporary backup is used during replacement so the previous installation can be restored. Source checkouts are not overwritten. Automatic updates can be disabled in Settings, and failures are recorded in `update.log`.

Release packages are built by GitHub Actions. The build jobs have read-only repository permissions; only the release-upload job has contents-write permission. Packages are not currently platform-signed, so Windows or macOS security controls can still require manual review or installation. Do not bypass OS warnings for packages obtained outside the official repository release.
