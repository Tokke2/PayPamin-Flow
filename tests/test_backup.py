import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from app_backup import (
    DATABASE_MEMBER,
    MANIFEST_MEMBER,
    BackupError,
    BackupPaths,
    create_backup,
    restore_backup,
)


class LocalBackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.paths = BackupPaths(
            database=self.root / "data" / "paminnelseapp.sqlite3",
            export_dir=self.root / "export",
            svg_dir=self.root / "svg",
            safety_dir=self.root / "data" / "backups",
        )
        self.paths.database.parent.mkdir(parents=True)
        self.paths.export_dir.mkdir()
        self.paths.svg_dir.mkdir()
        self.write_setting("language", "sv")
        with self.paths.database.open("ab"):
            pass
        (self.paths.export_dir / "reminder-1001.pdf").write_bytes(b"%PDF-reminder")
        (self.paths.svg_dir / "supplier.svg").write_text("<svg>supplier</svg>", encoding="utf-8")
        (self.root / "import").mkdir()
        (self.root / "import" / "invoice.pdf").write_bytes(b"private import")
        (self.root / "data" / "app.log").write_text("diagnostic", encoding="utf-8")

    def write_setting(self, key, value):
        connection = sqlite3.connect(self.paths.database)
        try:
            connection.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY,customer TEXT,note TEXT)"
            )
            connection.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            if key == "customer":
                connection.execute("INSERT INTO invoices(customer,note) VALUES(?,?)", (value, "reminder"))
            connection.commit()
        finally:
            connection.close()

    def test_backup_round_trip_restores_database_reminders_and_logos(self):
        self.write_setting("customer", "Original customer")
        destination = create_backup(self.root / "backup", self.paths)
        self.assertEqual(destination.suffix, ".zip")
        with zipfile.ZipFile(destination) as archive:
            names = set(archive.namelist())
            manifest = json.loads(archive.read(MANIFEST_MEMBER))
        self.assertIn(DATABASE_MEMBER, names)
        self.assertIn("export/reminder-1001.pdf", names)
        self.assertIn("svg/supplier.svg", names)
        self.assertNotIn("import/invoice.pdf", names)
        self.assertFalse(any(name.endswith("app.log") for name in names))
        self.assertEqual(manifest["application"], "PayPamin Flow")

        self.write_setting("language", "en")
        self.write_setting("customer", "Changed customer")
        (self.paths.export_dir / "reminder-1001.pdf").unlink()
        (self.paths.export_dir / "other.pdf").write_bytes(b"other")
        (self.paths.svg_dir / "supplier.svg").write_text("changed", encoding="utf-8")

        safety = restore_backup(destination, self.paths)
        self.assertTrue(safety.is_file())
        connection = sqlite3.connect(self.paths.database)
        try:
            language = connection.execute("SELECT value FROM settings WHERE key='language'").fetchone()[0]
            customers = [row[0] for row in connection.execute("SELECT customer FROM invoices ORDER BY id")]
        finally:
            connection.close()
        self.assertEqual(language, "sv")
        self.assertEqual(customers, ["Original customer"])
        self.assertEqual((self.paths.export_dir / "reminder-1001.pdf").read_bytes(), b"%PDF-reminder")
        self.assertFalse((self.paths.export_dir / "other.pdf").exists())
        self.assertEqual((self.paths.svg_dir / "supplier.svg").read_text(encoding="utf-8"), "<svg>supplier</svg>")

    def test_restore_rejects_path_traversal_without_touching_current_data(self):
        malicious = self.root / "malicious.zip"
        with zipfile.ZipFile(malicious, "w") as archive:
            archive.writestr("../outside.txt", "not allowed")
        with self.assertRaises(BackupError):
            restore_backup(malicious, self.paths)
        self.assertFalse((self.root / "outside.txt").exists())
        self.assertTrue(self.paths.database.is_file())

    def test_restore_rejects_modified_payload_and_keeps_current_files(self):
        destination = create_backup(self.root / "valid.zip", self.paths)
        tampered = self.root / "tampered.zip"
        with zipfile.ZipFile(destination) as source, zipfile.ZipFile(tampered, "w") as target:
            for info in source.infolist():
                content = source.read(info.filename)
                if info.filename == "export/reminder-1001.pdf":
                    content = b"tampered"
                target.writestr(info, content)
        original = (self.paths.export_dir / "reminder-1001.pdf").read_bytes()
        with self.assertRaises(BackupError):
            restore_backup(tampered, self.paths)
        self.assertEqual((self.paths.export_dir / "reminder-1001.pdf").read_bytes(), original)
        self.assertFalse(list(self.paths.safety_dir.glob("*.zip")))


if __name__ == "__main__":
    unittest.main()
