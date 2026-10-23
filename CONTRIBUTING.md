# Contributing

Thanks for considering a contribution.

1. Open an issue describing the change, using synthetic or anonymized examples only.
2. Do not commit customer invoices, generated reminders, local databases, logs, or company logos unless you have permission and intend to publish them.
3. Run the tests before opening a pull request:

   ```powershell
   py -m unittest discover -s tests -v
   ```

4. Keep invoice parsing changes covered by synthetic text fixtures. Never use real customer information in tests.
