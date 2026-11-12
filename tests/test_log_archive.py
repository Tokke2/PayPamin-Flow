import logging
import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from log_archive import (
    DailySizeRotatingFileHandler,
    RETENTION_DAYS,
    archive_old_logs,
    prune_expired_archives,
)


class LogArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.log_dir = Path(self.temporary.name) / "logs"
        self.log_dir.mkdir()

    @staticmethod
    def write_at(path, content, when):
        path.write_text(content, encoding="utf-8")
        timestamp = when.timestamp()
        os.utime(path, (timestamp, timestamp))

    def test_previous_days_archive_by_date_but_today_and_errors_stay(self):
        old_rotation = self.log_dir / "app.log.1"
        old_update = self.log_dir / "update.log"
        current = self.log_dir / "app.log"
        errors = self.log_dir / "errors.log"
        unrelated = self.log_dir / "notes.txt"
        self.write_at(old_rotation, "old app\n", datetime(2026, 11, 2, 23, 59))
        self.write_at(old_update, "older update\n", datetime(2026, 11, 1, 12, 0))
        self.write_at(current, "today app\n", datetime(2026, 11, 3, 0, 1))
        self.write_at(errors, "unresolved error\n", datetime(2026, 11, 1, 12, 0))
        self.write_at(unrelated, "keep\n", datetime(2026, 11, 1, 12, 0))

        report = archive_old_logs(self.log_dir, today=date(2026, 11, 3))

        self.assertEqual((report.archived, report.collisions, report.errors), (2, 0, 0))
        self.assertEqual((self.log_dir / "arkiv" / "2026-11-02" / "app.log.1").read_text(), "old app\n")
        self.assertEqual((self.log_dir / "arkiv" / "2026-11-01" / "update.log").read_text(), "older update\n")
        self.assertEqual(current.read_text(), "today app\n")
        self.assertEqual(errors.read_text(), "unresolved error\n")
        self.assertEqual(unrelated.read_text(), "keep\n")
        self.assertFalse(old_rotation.exists())
        self.assertFalse(old_update.exists())

    def test_archive_collision_uses_new_name_without_overwriting(self):
        source = self.log_dir / "app.log.1"
        self.write_at(source, "new archive copy\n", datetime(2026, 11, 2, 22, 0))
        dated = self.log_dir / "arkiv" / "2026-11-02"
        dated.mkdir(parents=True)
        (dated / "app.log.1").write_text("existing archive\n", encoding="utf-8")

        report = archive_old_logs(self.log_dir, today=date(2026, 11, 3))

        self.assertEqual((report.archived, report.collisions, report.errors), (1, 1, 0))
        self.assertEqual((dated / "app.log.1").read_text(), "existing archive\n")
        self.assertEqual((dated / "legacy-app.log.1").read_text(), "new archive copy\n")

    def test_archive_does_not_follow_symlinked_log(self):
        outside = Path(self.temporary.name) / "outside.log"
        outside.write_text("keep outside\n", encoding="utf-8")
        link = self.log_dir / "linked.log"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Symlinks are unavailable on this platform: {exc}")
        self.write_at(outside, "keep outside\n", datetime(2026, 11, 1, 12, 0))

        report = archive_old_logs(self.log_dir, today=date(2026, 11, 3))

        self.assertEqual(report.archived, 0)
        self.assertTrue(link.is_symlink())
        self.assertEqual(outside.read_text(), "keep outside\n")


    def test_archived_days_older_than_seven_are_deleted(self):
        archive = self.log_dir / "arkiv"
        for day in ("2026-10-26", "2026-10-27", "2026-11-02", "2026-11-03"):
            folder = archive / day
            folder.mkdir(parents=True)
            (folder / "app.log").write_text(f"log for {day}\n", encoding="utf-8")
        resolved = archive / "resolved" / "2026-10-25"
        resolved.mkdir(parents=True)
        (resolved / "errors-1.log").write_text("old resolved\n", encoding="utf-8")
        untouched = archive / "keep-me"
        untouched.mkdir()
        (untouched / "notes.txt").write_text("unrelated\n", encoding="utf-8")

        # Today is 2026-11-03: keep 2026-10-27..2026-11-03, drop anything older.
        report = archive_old_logs(self.log_dir, today=date(2026, 11, 3), retention_days=7)

        self.assertEqual(report.pruned_days, 2)
        self.assertFalse((archive / "2026-10-26").exists())
        self.assertFalse((archive / "resolved" / "2026-10-25").exists())
        self.assertTrue((archive / "2026-10-27").exists())
        self.assertTrue((archive / "2026-11-02").exists())
        self.assertTrue(untouched.exists())

    def test_retention_defaults_to_seven_days(self):
        self.assertEqual(RETENTION_DAYS, 7)
        archive = self.log_dir / "arkiv"
        (archive / "2026-11-02").mkdir(parents=True)
        (archive / "2026-11-03").mkdir(parents=True)

        # Seven days are kept in full: 2026-11-03 is exactly seven days old and
        # stays, while 2026-11-02 is deleted.
        removed, errors = prune_expired_archives(self.log_dir, today=date(2026, 11, 10))

        self.assertEqual((removed, errors), (1, 0))
        self.assertFalse((archive / "2026-11-02").exists())
        self.assertTrue((archive / "2026-11-03").exists())

    def test_retention_skips_symlinked_days_instead_of_following_them(self):
        outside = Path(self.temporary.name) / "outside-archive"
        outside.mkdir()
        (outside / "app.log").write_text("keep outside\n", encoding="utf-8")
        archive = self.log_dir / "arkiv"
        archive.mkdir()
        link = archive / "2026-10-01"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Symlinks are unavailable on this platform: {exc}")

        report = archive_old_logs(self.log_dir, today=date(2026, 11, 3))

        self.assertEqual(report.pruned_days, 0)
        self.assertTrue(link.is_symlink())
        self.assertEqual((outside / "app.log").read_text(), "keep outside\n")


class DailySizeRotationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "app.log"
        self.current = [date(2026, 11, 2)]
        self.handler = None

    def tearDown(self):
        if self.handler is not None:
            self.handler.close()

    def make_logger(self, **kwargs):
        self.handler = DailySizeRotatingFileHandler(
            self.path, maxBytes=kwargs.pop("maxBytes", 10000), backupCount=1,
            encoding="utf-8", today=lambda: self.current[0], **kwargs,
        )
        self.handler.setFormatter(logging.Formatter("%(message)s"))
        logger = logging.getLogger(f"log-archive-test-{id(self)}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.addHandler(self.handler)
        self.addCleanup(logger.removeHandler, self.handler)
        return logger

    def test_first_record_on_new_day_rotates_before_writing(self):
        logger = self.make_logger()
        logger.info("previous day")

        self.current[0] = date(2026, 11, 3)
        logger.info("current day")
        self.handler.flush()

        rotations = list(self.path.parent.glob("app.log.*"))
        self.assertEqual(len(rotations), 1)
        self.assertTrue(rotations[0].name.removeprefix("app.log.").isdigit())
        self.assertEqual(rotations[0].read_text(), "previous day\n")
        self.assertEqual(self.path.read_text(), "current day\n")

    def test_existing_old_active_file_rotates_on_first_new_day_record(self):
        self.path.write_text("old startup log\n", encoding="utf-8")
        timestamp = datetime(2026, 11, 2, 23, 0).timestamp()
        os.utime(self.path, (timestamp, timestamp))
        self.current[0] = date(2026, 11, 3)
        logger = self.make_logger()

        logger.info("new startup log")
        self.handler.flush()

        rotations = list(self.path.parent.glob("app.log.*"))
        self.assertEqual(len(rotations), 1)
        self.assertEqual(rotations[0].read_text(), "old startup log\n")
        self.assertEqual(self.path.read_text(), "new startup log\n")

    def test_size_rotation_does_not_delete_previous_rotations(self):
        logger = self.make_logger(maxBytes=35)
        for index in range(6):
            logger.info("size rotation record %d with padding", index)
        self.handler.flush()

        rotations = list(self.path.parent.glob("app.log.*"))
        self.assertGreaterEqual(len(rotations), 4)
        combined = self.path.read_text() + "".join(path.read_text() for path in rotations)
        for index in range(6):
            self.assertIn(f"size rotation record {index}", combined)


if __name__ == "__main__":
    unittest.main()
