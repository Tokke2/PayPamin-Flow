# Changelog

## Unreleased — application version remains 0.6.0

- Fixed paid reconciliation between different complete customer-ledger exports with the same list date. Previously seen unpaid invoices missing from the newly selected same-day list had been skipped because their last-seen date equalled the report date; they are now marked fully paid while manual/never-seen invoices remain protected. Older list dates are still rejected, repeated identical imports do not change paid amounts again, and invoice/reminder history is preserved.
- Replaced action icons with text-only labels on toolbar buttons, File/Help menus, the invoice context menu and dialog buttons in both languages. Commands and keyboard behavior are unchanged; the PayPamin Flow application/window/tray icon and horizontal header/About logo remain.
- Added detailed structured activity tracing to the existing technical log for Tk buttons, menus, context menus, tray actions, invoice selection/filter changes and update checks/installations. Start, completion/error, duration, result type, session/action IDs and timezone-aware timestamps are recorded without changing the original command result; registered Tk command names and Python callbacks are both supported, unexpected Tk callback exceptions are retained, and log rotation was increased to 5 MB with five history files. Existing domain-specific PDF, ledger, email, backup and background diagnostics remain.
- Added **Update app** to the system-tray right-click menu between Open and Exit. It restores the window and starts the same manual update flow as the Help menu; the tray label follows available/checking/installing states and refreshes with the main update button.
- Successful customer-ledger imports now return the main view to **Current**, so invoices reconciled as paid leave the active working list immediately even if **All** was selected. Their database records and P1/P2/email history remain available under **All** rather than being deleted.
- Fixed customer-ledger paid reconciliation for invoices that already existed in both the app and the selected PDF. Existing rows previously received only first/last-seen timestamps while the parsed Belopp/Saldo payment was ignored; verified SEK imports now increase their paid amount from the current row, mark zero-balance rows fully paid and include listed payment updates in the result and technical log. A zero balance remains authoritative after a historic app-amount correction, partial payments with differing amounts are not guessed, higher existing payments are never reduced, non-SEK safeguards remain, and invoice fields plus P1/P2/email history are preserved. Reimporting the same latest list can therefore repair existing rows without requiring a newer list date.
- Introduced a complete new visual identity: a new invoice/P/check app icon, an editable horizontal PayPamin Flow logo for the header and About window, and 31 coordinated action icons with normal and light transparent variants. Icons now cover File/Help and context menus, both toolbar rows and known dialog buttons in Swedish and English through a shared recursive icon manager. Regenerated PNG/ICO/ICNS assets are used by the existing tray, Windows small/large window handles, taskbar/Task Manager app view, macOS Dock, Linux and autostart branding paths; the toolbar was split into two rows to remain readable with icons.
- Customer-ledger imports now apply immediately after the selected PDF passes validation, without the previous yes/no review dialog. Previously seen invoices missing from a later complete SEK ledger are automatically marked fully paid in the same atomic import; their records and reminder history are preserved. First-list history building, never-seen/manual-invoice protection, older-list rejection and non-SEK no-reconciliation safeguards remain, and validation failures still block every change.
- Customer-ledger imports now preserve a non-empty reference/invoice-text field on new invoice records so it reaches the P1/P2 PDF as **Avser/Reference**. Empty or whitespace-only text omits the entire row and its vertical space instead of printing the old fallback sentence, and the specification table moves up. Later ledger imports do not overwrite an existing invoice's saved text. Existing PDFs and reminder history are not rewritten automatically.
- Added actual local visual invoice-logo matching against the same supplier SVG already stored directly in `svg/` and used for P1/P2 export; no extra image folder or duplicate reference is needed. Scale/position-tolerant SIFT features, projective geometry checks, high acceptance thresholds and a clear-winner rule prevent weak or tied visual guesses. Exact identifiers and textual matches retain priority, visual ambiguity never falls back to a company-name guess, multi-invoice bundles skip whole-page visual guessing, and broken/missing references or OpenCV leave the existing review workflow intact. Added real synthetic-PDF tests for correct, resized/repositioned, wrong, shared and broken logos and included the headless OpenCV dependency in normal installs and desktop CI.
- Improved supplier/template matching during PDF import with persistent, editable organisation and bankgiro numbers, exact labelled-identifier matching, normalized supplier names and logo aliases from SVG filenames/title/text metadata. Conflicting or tied matches remain unresolved instead of falling back to a risky guess; legacy zone-only templates remain available. The PDF review now has an editable supplier dropdown and validated identifier fields, duplicate identifiers are blocked, and identifiers survive SQLite migration, JSON export/restore and ordinary database backups without old journals erasing local values. Textual logo aliases remain available alongside the separate visual matcher.
- Added text-based Fortnox customer-ledger PDF import with page/count/total validation, a once-per-Friday import reminder and automatic paid reconciliation after validation. The first list establishes history; only previously seen invoices missing from a later complete list can be marked paid, while existing invoice edits and P1/P2 history are preserved and ledger metadata survives JSON backup/restore.
- Strengthened Windows icon branding by setting native small and large PayPamin Flow icons directly on the main window and every secondary window handle for the taskbar and Task Manager app view, with shared process-lifetime HICONs and safe Tk fallback. Task Manager's Details/background-process views can still use pythonw.exe's embedded icon; changing that would require the native EXE that the Python-only distribution intentionally does not include.
- Added status-based invoice-row backgrounds: green for invoices due today or later without P1/P2, yellow when P1 is due or exists without an active P2, and red when P2 is due or exists. Paid, ignored, unreviewed and invalid-date rows remain neutral, P2 takes precedence, and the written status remains visible.
- Added detailed local customer-ledger diagnostics before import: source filename, list date, page/invoice counts, expected/actual totals, every parsed invoice row and every paid-reconciliation candidate are written as structured technical-log records, including validation failures that stop the import. **Help → View technical log** opens the complete `app.log`; raw PDF text is not dumped and the consolidated error log remains error-only.
- Added a local consolidated `errors.log` for faster troubleshooting. It collects complete error/traceback blocks from current and rotated app logs, startup failures and update failures, newest first with duplicate suppression and atomic refreshes, while preserving every original log. The toolbar and Help menu open the consolidated view directly.
- Replaced native application packaging with one cross-platform `PayPamin-Flow-Python.zip` and SHA-256 sidecar; removed PyInstaller and native build metadata.
- Added validated in-app installation of Python updates with atomic replacement, rollback and console-free restart; no separate updater needs to be run by the user.
- Kept the old app alive until the updated process confirms UI readiness with a one-off PID/token handshake; startup timeout or early exit stops the failed child and rolls back safely.
- Made **Update app** a prominent stateful button: it changes to **Update available**, reopens the known release without another network request, retains progress states and offers **Check again** for a forced fresh GitHub check.
- Improved manual and automatic GitHub release updates: automatic installation waits for complete ZIP/SHA-256 assets, the manual dialog shows update reason and installed/release commits with incomplete-file protection, installation stages are visible in the update button, and official builds show their commit in About.
- Kept transient CI `test-results.txt` out of release packages and the update allowlist so manifests contain only application files.
- Added same-version comparison of the full release commit and a manifest containing SHA-256 for every shipped file. A changed commit or file fingerprint triggers an update; a new release ID with identical commit/files does not reinstall. Older official builds retain the release-ID fallback, and new-manifest packages must match their commit, release identity and file fingerprint before installation.
- Added official GitHub release-ID comparison so a refreshed release build can be installed without changing the application version; update checks still use Releases rather than the main branch.
- Replaced Windows registry autostart with an atomic per-user Startup shortcut carrying the PayPamin Flow icon. The shortcut uses `pythonw.exe` with the shared `paypamin_flow_launcher.py`, never `.pyw`; legacy Run entries are removed after successful migration to prevent duplicate launches. Manual launchers and update restarts use the same diagnostic launcher, while the old `.pyw` remains only as a compatibility entry point.
- Prevented Windows console windows from PDF/OCR and other child processes while preserving existing subprocess flags; GUI launch and autostart continue to use `pythonw.exe`.
- Fixed tray startup through pystray's detached GUI integration and backend-ready visibility callback; added a distinct Windows taskbar app identity and mandatory validation of every application icon in Python updates.
- Added close-to-system-tray behavior, an explicit full-exit path and the PayPamin Flow icon in the tray.
- Added minimize-to-system-tray behavior for the window-manager minimize button, without retriggering on the app's own withdraw and with safe restoration if the tray is unavailable.
- Added bilingual File-menu backup and restore for settings, invoices, reminders, templates and logos, including checksum/SQLite validation and a pre-restore safety backup.
- Added File and Help menus, with update checks available inside the app and automatic checks retained every 12 hours.
- Added license-free Fortnox PDF import with automatic folder monitoring, stable-file detection, reviewed imports, duplicate suppression and an automatic-import setting.
- Added right-click **Edit customer** with reusable, validated comma-separated email recipients; contacts are learned on invoice saves, restored through JSON and reused for future invoices for the same customer.
- Added OS-default email drafts after reminder generation with all customer recipients, a fixed BCC to `rl@tadega.com`, polished Swedish/English P1/P2 text and no automatic sending; standard `mailto:` clients require manual PDF attachment because they do not provide consistent attachment support.
- Added right-click **Create email draft** for recipients added or changed after reminder generation. The action uses current customer contacts and the latest existing level (P2, otherwise P1), preserves P1/P2 snapshot amounts and deadlines, finds existing/archived or legacy-event PDFs without rewriting them, and never changes reminder history or sends automatically.
- Added an in-app email preview for both generated and right-click drafts. It shows fixed recipients/BCC, the PDF path and whether attachment is automatic, allows temporary subject/body edits, and records or opens nothing when cancelled.
- Reworked automatic Thunderbird PDF attachment after repeated real Windows 11 compose-window failures. Recipients, fixed BCC, edited subject/body and the exact PDF now go into a temporary `X-Unsent: 1` MIME `.eml` draft, which Thunderbird 91+ opens directly for manual review and sending without the fragile `-compose attachment=` parser. Failed launches remove the temporary file; only PayPamin Flow's own temporary drafts older than 24 hours are cleaned later. Windows 11 `UserChoice`, registered commands and custom-path detection remain, as do empty-PDF checks, immediate-launch errors, no-console launching and the standard `mailto:`/manual-attachment fallback for other clients.
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
