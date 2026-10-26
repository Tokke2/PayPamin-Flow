# Contributing

Thanks for considering a contribution to PayPamin Flow.

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
8. Keep release asset names in `app_info.py`, `packaging/package_release.py` and the updater consistent. Test update downloads with synthetic packages and checksums; never run replacement helpers against a real development or production installation.

PayPamin Flow is created by Rickard Länkvist. Copyright © 2026 Rickard Länkvist.
