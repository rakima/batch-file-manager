from __future__ import annotations

import json
import os
from pathlib import Path


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        base = Path(os.getenv("APPDATA", Path.home())) / "BatchFileManager"
        self.path = path or base / "settings.json"

    def load(self) -> dict[str, str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return {str(key): str(value) for key, value in data.items()}
        except (OSError, json.JSONDecodeError, TypeError):
            return {}

    def save(self, settings: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(self.path)

