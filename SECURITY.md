# Security and sensitive data

PayPamin Flow processes invoice PDFs and customer data. Do not attach real invoices, exported reminders, the local SQLite database, or unredacted logs to public GitHub issues or pull requests.

For a bug report, use synthetic or thoroughly anonymized examples. The app is a prototype; review each extracted field and generated reminder before use. Report security concerns privately to the repository maintainer rather than opening a public issue.

Autostart entries are created only for the current OS user and can be disabled in Settings. They launch the same local application and do not add a network service.

## Automatic updates

Automatic updates retrieve only stable releases from the project's GitHub repository over HTTPS. The shared Python package must include a matching SHA-256 file, and the package is verified before extraction. Download URLs and redirects are restricted to trusted GitHub hosts. Archive paths, file types, member counts and sizes are restricted, symbolic links are rejected, and Python files are syntax-checked before installation.

Only application-owned Python source, launchers, documentation and icon files are replaced. The database, `import/`, `export/`, `svg/` and other local business data are not valid package paths and are not part of update requests. A temporary rollback copy is used during replacement so the previous files can be restored if installation or restart fails. Automatic updates can be disabled in Settings, and failures are recorded in `update.log`.

Release packages are built by GitHub Actions. The test jobs have read-only repository permissions; only the release-upload job has contents-write permission. Download Python packages only from the official repository release.

## Local backups

Backup ZIP files contain sensitive settings, invoice data, reminders and supplier logos. Store them with the same care as the original database and do not upload them to public issues. Restore validates archive paths, allowed file locations, duplicate entries, sizes, SHA-256 checksums and SQLite integrity before replacing data. A separate safety backup of current data is created under `~/.paminnelseapp/backups` before every restore.
