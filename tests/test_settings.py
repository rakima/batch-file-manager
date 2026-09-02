from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from batch_file_manager.services.settings import SettingsStore


class SettingsStoreTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            store.save({"last_folder": "C:/files", "geometry": "1200x800"})

            self.assertEqual(
                {"last_folder": "C:/files", "geometry": "1200x800"}, store.load()
            )

    def test_invalid_json_returns_empty_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("invalid", encoding="utf-8")

            self.assertEqual({}, SettingsStore(path).load())


if __name__ == "__main__":
    unittest.main()
