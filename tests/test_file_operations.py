from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from batch_file_manager.models import RenamePosition, TimestampUpdate
from batch_file_manager.services.file_operations import FileOperationService


class FileOperationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.service = FileOperationService()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def create_file(self, name: str) -> Path:
        path = self.root / name
        path.write_text("test", encoding="utf-8")
        return path

    def test_rename_positions(self) -> None:
        path = self.create_file("sample.txt")
        cases = [
            (RenamePosition.PREFIX, "test_sample.txt"),
            (RenamePosition.BEFORE_EXTENSION, "sampletest_.txt"),
            (RenamePosition.SUFFIX, "sample.txttest_"),
        ]
        for position, expected in cases:
            with self.subTest(position=position):
                change = self.service.plan_rename([path], "test_", position)[0]
                self.assertEqual(expected, change.destination.name)

    def test_existing_destination_is_not_overwritten(self) -> None:
        source = self.create_file("source.txt")
        existing = self.create_file("x_source.txt")
        change = self.service.plan_rename([source], "x_", RenamePosition.PREFIX)

        result = self.service.apply_changes(change)[0]

        self.assertFalse(result.success)
        self.assertTrue(source.exists())
        self.assertEqual("test", existing.read_text(encoding="utf-8"))

    def test_move_continues_after_an_individual_failure(self) -> None:
        first = self.create_file("first.txt")
        second = self.create_file("second.txt")
        destination = self.root / "destination"
        destination.mkdir()
        (destination / "first.txt").write_text("existing", encoding="utf-8")

        results = self.service.apply_changes(
            self.service.plan_move([first, second], destination)
        )

        self.assertFalse(results[0].success)
        self.assertTrue(results[1].success)
        self.assertTrue(first.exists())
        self.assertTrue((destination / "second.txt").exists())

    def test_updates_modified_and_accessed_times(self) -> None:
        path = self.create_file("time.txt")
        value = datetime(2024, 5, 6, 7, 8, 9)

        result = self.service.update_timestamps(
            [path], TimestampUpdate(modified=value, accessed=value)
        )[0]

        self.assertTrue(result.success)
        self.assertAlmostEqual(value.timestamp(), path.stat().st_mtime, delta=1)
        self.assertAlmostEqual(value.timestamp(), path.stat().st_atime, delta=1)

    def test_formats_datetime_presets(self) -> None:
        value = datetime(2026, 9, 2, 15, 4, 5)
        self.assertEqual("20260902", self.service.format_datetime("YYYYMMDD", value))
        self.assertEqual("2026-09-02", self.service.format_datetime("YYYY-MM-DD", value))
        self.assertEqual(
            "20260902_150405", self.service.format_datetime("YYYYMMDD_HHmmss", value)
        )
        self.assertEqual("150405", self.service.format_datetime("HHmmss", value))


if __name__ == "__main__":
    unittest.main()

