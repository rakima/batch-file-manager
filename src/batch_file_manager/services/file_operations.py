from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable

from batch_file_manager.models import (
    OperationKind,
    OperationResult,
    PlannedChange,
    RenamePosition,
    TimestampUpdate,
)


DATE_FORMATS = {
    "YYYYMMDD": "%Y%m%d",
    "YYYY-MM-DD": "%Y-%m-%d",
    "YYYYMMDD_HHmmss": "%Y%m%d_%H%M%S",
    "HHmmss": "%H%M%S",
}


class FileOperationService:
    """Builds non-mutating plans and executes each file operation independently."""

    def plan_move(self, paths: Iterable[Path], destination_dir: Path) -> list[PlannedChange]:
        return [
            PlannedChange(OperationKind.MOVE, path, destination_dir / path.name)
            for path in self._files(paths)
        ]

    def plan_rename(
        self,
        paths: Iterable[Path],
        text: str,
        position: RenamePosition,
    ) -> list[PlannedChange]:
        changes: list[PlannedChange] = []
        for path in self._files(paths):
            new_name = self._renamed_name(path, text, position)
            changes.append(PlannedChange(OperationKind.RENAME, path, path.with_name(new_name)))
        return changes

    def apply_changes(self, changes: Iterable[PlannedChange]) -> list[OperationResult]:
        changes = list(changes)
        duplicate_targets = self._duplicate_targets(changes)
        results: list[OperationResult] = []

        for change in changes:
            try:
                self._validate_change(change, duplicate_targets)
                if change.kind is OperationKind.MOVE:
                    shutil.move(str(change.source), str(change.destination))
                else:
                    change.source.rename(change.destination)
                results.append(
                    OperationResult(change.source, True, "完了", change.destination)
                )
            except (OSError, ValueError) as exc:
                results.append(
                    OperationResult(change.source, False, str(exc), change.destination)
                )
        return results

    def update_timestamps(
        self, paths: Iterable[Path], update: TimestampUpdate
    ) -> list[OperationResult]:
        results: list[OperationResult] = []
        for path in self._files(paths):
            try:
                stat = path.stat()
                accessed = update.accessed.timestamp() if update.accessed else stat.st_atime
                modified = update.modified.timestamp() if update.modified else stat.st_mtime
                os.utime(path, (accessed, modified))
                if update.created is not None:
                    self._set_creation_time(path, update.created)
                results.append(OperationResult(path, True, "タイムスタンプを更新しました"))
            except (OSError, ValueError) as exc:
                results.append(OperationResult(path, False, str(exc)))
        return results

    @staticmethod
    def format_datetime(preset: str, value: datetime | None = None) -> str:
        try:
            pattern = DATE_FORMATS[preset]
        except KeyError as exc:
            raise ValueError(f"未対応の日時形式です: {preset}") from exc
        return (value or datetime.now()).strftime(pattern)

    @staticmethod
    def _files(paths: Iterable[Path]) -> list[Path]:
        return [Path(path) for path in paths if Path(path).is_file()]

    @staticmethod
    def _renamed_name(path: Path, text: str, position: RenamePosition) -> str:
        if position is RenamePosition.PREFIX:
            return f"{text}{path.name}"
        if position is RenamePosition.BEFORE_EXTENSION:
            return f"{path.stem}{text}{path.suffix}"
        return f"{path.name}{text}"

    @staticmethod
    def _duplicate_targets(changes: list[PlannedChange]) -> set[Path]:
        counts: dict[Path, int] = {}
        for change in changes:
            key = change.destination.resolve()
            counts[key] = counts.get(key, 0) + 1
        return {path for path, count in counts.items() if count > 1}

    @staticmethod
    def _validate_change(change: PlannedChange, duplicate_targets: set[Path]) -> None:
        if not change.source.is_file():
            raise ValueError("元ファイルが存在しません")
        if change.source.resolve() == change.destination.resolve():
            raise ValueError("変更前と変更後が同じです")
        if change.destination.resolve() in duplicate_targets:
            raise ValueError("複数ファイルの変更先が重複しています")
        if change.destination.exists():
            raise FileExistsError("同名のファイルが既に存在します")
        if not change.destination.parent.is_dir():
            raise FileNotFoundError("変更先フォルダが存在しません")

    @staticmethod
    def _set_creation_time(path: Path, value: datetime) -> None:
        if os.name != "nt":
            raise OSError("作成日時の変更はWindowsでのみ利用できます")

        creation_time = int((value.timestamp() + 11644473600) * 10_000_000)
        low = creation_time & 0xFFFFFFFF
        high = creation_time >> 32
        file_time = ctypes.wintypes.FILETIME(low, high)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = (
            ctypes.wintypes.LPCWSTR,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.HANDLE,
        )
        kernel32.CreateFileW.restype = ctypes.wintypes.HANDLE
        kernel32.SetFileTime.argtypes = (
            ctypes.wintypes.HANDLE,
            ctypes.POINTER(ctypes.wintypes.FILETIME),
            ctypes.c_void_p,
            ctypes.c_void_p,
        )
        kernel32.SetFileTime.restype = ctypes.wintypes.BOOL
        kernel32.CloseHandle.argtypes = (ctypes.wintypes.HANDLE,)
        kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
        handle = kernel32.CreateFileW(
            str(path), 0x0100, 0x00000007, None, 3, 0x80, None
        )
        if handle == ctypes.wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not kernel32.SetFileTime(handle, ctypes.byref(file_time), None, None):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel32.CloseHandle(handle)
