# Changelog

## Unreleased — application version remains 0.6.0

- Replaced native application packaging with one cross-platform `PayPamin-Flow-Python.zip` and SHA-256 sidecar; removed PyInstaller and native build metadata.
- Added validated in-app installation of Python updates with atomic replacement, rollback and console-free restart; no separate updater needs to be run by the user.
- Kept the old app alive until the updated process confirms UI readiness with a one-off PID/token handshake; startup timeout or early exit stops the failed child and rolls back safely.
- Added official GitHub release-ID comparison so a refreshed release build can be installed without changing the application version; update checks still use Releases rather than the main branch.
- Prevented Windows console windows from PDF/OCR and other child processes while preserving existing subprocess flags; GUI launch and autostart continue to use `pythonw.exe`.
- Fixed tray startup through pystray's detached GUI integration and backend-ready visibility callback; added a distinct Windows taskbar app identity and mandatory validation of every application icon in Python updates.
- Added close-to-system-tray behavior, an explicit full-exit path and the PayPamin Flow icon in the tray.
- Added minimize-to-system-tray behavior for the window-manager minimize button, without retriggering on the app's own withdraw and with safe restoration if the tray is unavailable.
- Added bilingual File-menu backup and restore for settings, invoices, reminders, templates and logos, including checksum/SQLite validation and a pre-restore safety backup.
- Added File and Help menus, with update checks available inside the app and automatic checks retained every 12 hours.
- Added license-free Fortnox PDF import with automatic folder monitoring, stable-file detection, reviewed imports, duplicate suppression and an automatic-import setting.
- Added right-click **Edit customer** with reusable, validated comma-separated email recipients; contacts are learned on invoice saves, restored through JSON and reused for future invoices for the same customer.
- Added OS-default email drafts after reminder generation with all customer recipients, a fixed BCC to `rl@tadega.com`, polished Swedish/English P1/P2 text and no automatic sending; the generated PDF is attached manually because standard `mailto:` handlers do not provide consistent attachments.
- Added right-click **Create email draft** for recipients added or changed after reminder generation. The action uses current customer contacts and the latest existing level (P2, otherwise P1), preserves P1/P2 snapshot amounts and deadlines, finds existing/archived or legacy-event PDFs without rewriting them, and never changes reminder history or sends automatically.
- Added an in-app email preview for both generated and right-click drafts. It shows fixed recipients/BCC and the manual PDF path, allows temporary subject/body edits, and records or opens nothing when cancelled.
- Separated PDF creation, draft-opened and manually confirmed sent status per P1/P2 level. The list highlights the latest level and details show both existing levels, P1 status survives P2 creation, all four dates migrate through SQLite and JSON/ZIP backup restore, and reminder events/sent count are unchanged; corrected the P2 list label from “Sent” to “Created”.
- Kept the invoice number in a common P1/P2 subject and added **SV:/Re:** for P2 and previously sent reminders as best-effort mail-client threading. Standard `mailto:` cannot search a mailbox, discover an existing conversation or guarantee an actual reply; users must continue that conversation manually if their mail client does not associate the draft.
- Allowed one **Create reminder** click to create/recreate P1 and continue to due P2, while preserving original P1 history and respecting both the configured P2 interval and the payment deadline stored in the P1 snapshot.
- Improved invoice PDF parsing with English payable labels, safe Swedish/European/English number normalization, currency detection near totals and safeguards against reading VAT, subtotals, invoice numbers or dates as the payable amount.
- Improved learned amount and invoice-text zones with the same conservative payable-total parser, whole-number amounts, explicit/multiline `Fakturatext`/`Avser` handling and table-value cleanup; ambiguous unlabelled amount zones no longer overwrite an existing suggestion.
- Added import of multiple invoices from one PDF, including multi-page invoice sections, per-invoice review/page ranges and stable per-section duplicate handling that can resume partially imported bundles.
- Added conservative smart cache cleanup with manual and once-daily automatic modes, 24-hour age/type filters and strict protection for invoices, import files, settings and backups.
- Added one-click paid marking and paid-invoice import suppression by invoice number or PDF identity, with silent automatic skips and separate manual summary counts.
- Fixed modal PDF preview lockups by dismissing lingering invoice menus, delaying the preview grab until rendering succeeds, releasing it on every close and reporting template-save errors without trapping the window.
- Applied the PayPamin Flow PNG and native Windows icon explicitly to every secondary app window through one shared window factory.
- Preserved the supplier logo selected during PDF matching on the invoice itself and used it for P1/P2 export even without saving field zones, after restart or after changing the global logo.
- Added **Edit P1** and **Edit P2** in the toolbar and context menu for replacing either level's logo and atomically regenerating its original PDF without changing reminder dates, history or sent count; failed writes preserve the previous PDF and invoice selection, and no email draft is opened.
- Added internal P1/P2 snapshots for original invoice data, fee, interest, payment deadline, objection terms and language, with safe legacy-row handling and P2 snapshot persistence through SQLite migrations and JSON restore; older P2s freeze their values on the first successful edit. Broken SVG logos now show an error instead of silently generating a text-logo PDF.
- Added pre-P1 verification against the original invoice PDF, including saved field zones and multi-invoice section matching; mismatches stop creation without changing invoice or reminder history.
- Added safe recreation of a missing P1 PDF from its original snapshot, date, terms and logo without adding a reminder event or changing P2/history counters.
- Added an in-app **Open export folder** button and File-menu command for opening generated reminder PDFs in the system file manager.
- Added a bilingual post-scan dialog listing invoices ready for P1/P2 using the existing workflow rules; paid, ignored, unreviewed and waiting invoices are excluded and no reminder is created automatically.
- Added automatic non-destructive archiving of recognized P1/P2 PDFs more than seven days old to `export/arkiv/`; archived P1s remain editable, invoice/journal history is unchanged and existing archive files are never overwritten.
- Added minimized OS-login autostart through a shared `--minimized` argument on Windows, macOS and Linux; manual launches remain visible and existing login entries are refreshed automatically.
- Made the shared console-free launcher report import/startup failures with a native message and `~/.paminnelseapp/startup.log`; normal launch, autostart and update restart use the same entry point on all three platforms.
- Removed obsolete legacy module duplicates and native-build leftovers; only active Python launchers and application files are shipped.
- Added an atomic JSON journal with invoice data, customer contacts, settings, learned templates/zone samples, logos and persistent reminder history; it now refreshes immediately after invoice/customer/template/settings/logo/status saves as well as successful P1/P2 generation, with visible write-error reporting. Legacy reminder dates are included and imported local customer contacts are not overwritten.
- Added one automatic JSON backup per ISO week while the app is running, a matching atomic ZIP of the import/export folders, and bilingual File-menu import for reinstall recovery, with duplicate-safe invoice/event merging.
- Added headless backup, tray, import-watcher, Python-package, updater, rollback and console-free restart tests.

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
