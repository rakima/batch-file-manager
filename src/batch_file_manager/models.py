from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path


class RenamePosition(str, Enum):
    PREFIX = "prefix"
    BEFORE_EXTENSION = "before_extension"
    SUFFIX = "suffix"


class OperationKind(str, Enum):
    MOVE = "move"
    RENAME = "rename"


@dataclass(frozen=True)
class PlannedChange:
    kind: OperationKind
    source: Path
    destination: Path


@dataclass(frozen=True)
class TimestampUpdate:
    modified: datetime | None = None
    accessed: datetime | None = None
    created: datetime | None = None


@dataclass(frozen=True)
class OperationResult:
    source: Path
    success: bool
    message: str
    destination: Path | None = None

