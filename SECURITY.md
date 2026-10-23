# Security and sensitive data

PayPamin Flow processes invoice PDFs and customer data. Do not attach real invoices, exported reminders, the local SQLite database, or unredacted logs to public GitHub issues or pull requests.

For a bug report, use synthetic or thoroughly anonymized examples. The app is a prototype; review each extracted field and generated reminder before use. Report security concerns privately to the repository maintainer rather than opening a public issue.

Autostart entries are created only for the current OS user and can be disabled in Settings. They launch the same local application and do not add a network service.
