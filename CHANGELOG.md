# Changelog

## Unreleased — application version remains 0.6.0

- Replaced native application packaging with one cross-platform `PayPamin-Flow-Python.zip` and SHA-256 sidecar; removed PyInstaller and native build metadata.
- Added validated in-app installation of Python updates with atomic replacement, rollback and console-free restart; no separate updater needs to be run by the user.
- Added close-to-system-tray behavior, an explicit full-exit path and the PayPamin Flow icon in the tray.
- Added bilingual File-menu backup and restore for settings, invoices, reminders, templates and logos, including checksum/SQLite validation and a pre-restore safety backup.
- Added File and Help menus, with update checks available inside the app and automatic checks retained every 12 hours.
- Added headless backup, tray, Python-package, updater, rollback and console-free restart tests.

## 0.6.0 — 2026-10-26

- Close SQLite connections deterministically after each transaction so Windows does not retain locked database files.
- Guaranteed console-free Windows source autostart by requiring `pythonw.exe` instead of falling back to a console interpreter; added native and manual launcher coverage for all three desktop platforms.
- Prevented duplicate invoice imports and manual entries using normalized invoice numbers and PDF content hashes, including renamed files; added bilingual warnings and duplicate counts in folder-scan results.
- Added silent GitHub release checks shortly after startup and every 12 hours while the app is open, plus a **Check for updates** button and an automatic-update setting.
- Added automatic download, SHA-256 verification, safe extraction, native installation and silent restart for newer stable releases on Windows, macOS and Linux.
- Added manual **Install and restart** and **Open download page** choices; source checkouts and automatic failures retain a manual update path.
- Preserved invoice data, settings and templates, added rollback during native replacement and kept automatic failures unobtrusive.
- Added release packaging for all three desktop platforms and per-package SHA-256 assets, uploaded by a restricted GitHub Actions release job.
- Added headless tests for release responses, scheduling, checksum verification, archive safety, native packaging, update UI behavior and a real synthetic Linux replacement/restart.

## 0.5.0 — 2026-10-23

- Published release v0.5.0 with per-invoice currencies, Swedish and English interfaces, localized reminder PDFs, native per-user autostart and Windows/macOS/Linux build support.
- Preserved existing local invoice/template data and Tadega AB reminder content.
- Verified with 31 automated tests and headless Swedish/English EUR reminder PDF checks.

## 0.4.0 — 2026-10-23

- Added an editable three-letter currency code to every invoice, with SEK as the default for new and previously saved invoices.
- Added currency suggestions from PDF text and reusable marked PDF fields; all suggestions remain subject to invoice review.
- Applied the invoice currency consistently to amounts, paid/outstanding values, reminder fees, confirmations and generated reminder PDFs in Swedish and English.
- Kept amounts in their original currency without exchange-rate lookup or conversion; reminder fee numbers now follow each invoice's currency.
- Added currency formatting, parser and real SQLite migration tests, including preservation of existing invoice amounts.

## 0.3.0 — 2026-10-23

- Added complete Swedish and English language support with a persistent **Svenska / English** selector in Settings.
- Language changes rebuild the main window immediately without restarting or changing saved invoice/template data.
- Localized statuses, filters, amounts, dates, dialogs, PDF preview, validation messages, autostart errors and Linux desktop metadata.
- Localized generated reminder PDFs, including P2 warnings, fees, payment terms and file names.
- Added translation completeness, placeholder, language switching and locale-independent date tests.

## 0.2.0 — 2026-10-23

- Changed the product name to **PayPamin Flow** throughout the UI, launchers, documentation and native package metadata.
- Added creator and copyright attribution for **Rickard Länkvist**, including an in-app About dialog and a `NOTICE` file.
- Added one custom application icon in SVG, PNG, ICO and ICNS formats for windows, dialogs and native desktop packages.
- Added per-user login autostart for Windows, macOS and Linux, enabled by default and configurable in Settings.
- Added macOS and Linux launchers, cross-platform file opening, portable UI fonts and writable data paths for frozen apps.
- Added PyInstaller configuration, Windows/macOS metadata, Linux desktop integration and a three-OS GitHub Actions build matrix.
- Separated invoice parsing from Tkinter and added autostart and branding tests.

## 0.1.0 — GitHub preparation

- Initial source release of the local prototype.
- Individual invoice PDF import, field preview/matching templates, and PDF reminder export.
- Manual review gate, local diagnostic logging, supplier-linked SVG logo matching, import/export folders, and Windows no-console launcher.
