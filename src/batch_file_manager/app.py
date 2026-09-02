from __future__ import annotations

import os
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from batch_file_manager.models import PlannedChange, RenamePosition, TimestampUpdate
from batch_file_manager.services.file_operations import DATE_FORMATS, FileOperationService
from batch_file_manager.services.settings import SettingsStore


DATETIME_INPUT_FORMAT = "%Y-%m-%d %H:%M:%S"
POSITION_LABELS = {
    "先頭": RenamePosition.PREFIX,
    "拡張子の前": RenamePosition.BEFORE_EXTENSION,
    "末尾": RenamePosition.SUFFIX,
}


class BatchFileManagerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.service = FileOperationService()
        self.settings_store = SettingsStore()
        self.settings = self.settings_store.load()
        self.current_folder: Path | None = None
        self.item_paths: dict[str, Path] = {}
        self.pending_changes: list[PlannedChange] = []
        self.pending_timestamp: tuple[list[Path], TimestampUpdate] | None = None

        self.folder_var = tk.StringVar(value="フォルダが選択されていません")
        self.move_destination_var = tk.StringVar()
        self.rename_text_var = tk.StringVar()
        self.rename_position_var = tk.StringVar(value="先頭")
        self.use_datetime_var = tk.BooleanVar(value=False)
        self.datetime_preset_var = tk.StringVar(value="YYYYMMDD")
        self.timestamp_value_var = tk.StringVar(
            value=datetime.now().strftime(DATETIME_INPUT_FORMAT)
        )
        self.modify_time_var = tk.BooleanVar(value=True)
        self.access_time_var = tk.BooleanVar(value=False)
        self.create_time_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="準備完了")

        self._configure_window()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._restore_folder()

    def _configure_window(self) -> None:
        self.root.title("Batch File Manager")
        self.root.geometry(self.settings.get("geometry", "1200x780"))
        self.root.minsize(900, 620)
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Treeview", rowheight=24)
        style.configure("TLabelframe", padding=8)

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(container)
        top.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(top, text="選択中フォルダ:").pack(side=tk.LEFT)
        ttk.Label(top, textvariable=self.folder_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=8
        )
        ttk.Button(top, text="フォルダを選択", command=self._choose_folder).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(top, text="更新", command=self.refresh_tree).pack(side=tk.LEFT)

        vertical = ttk.Panedwindow(container, orient=tk.VERTICAL)
        vertical.pack(fill=tk.BOTH, expand=True)
        workspace = ttk.Panedwindow(vertical, orient=tk.HORIZONTAL)
        vertical.add(workspace, weight=3)

        tree_frame = ttk.LabelFrame(workspace, text="ファイル一覧（Ctrl/Shiftで複数選択）")
        workspace.add(tree_frame, weight=3)
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("type", "modified", "size"),
            selectmode="extended",
        )
        self.tree.heading("#0", text="ファイル名", anchor=tk.W)
        self.tree.heading("type", text="種別", anchor=tk.W)
        self.tree.heading("modified", text="更新日時", anchor=tk.W)
        self.tree.heading("size", text="サイズ", anchor=tk.E)
        self.tree.column("#0", width=330, minwidth=180)
        self.tree.column("type", width=90, stretch=False)
        self.tree.column("modified", width=150, stretch=False)
        self.tree.column("size", width=90, stretch=False, anchor=tk.E)
        tree_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        tree_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_y.set, xscrollcommand=tree_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_y.grid(row=0, column=1, sticky="ns")
        tree_x.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        notebook = ttk.Notebook(workspace)
        workspace.add(notebook, weight=2)
        self._build_move_tab(notebook)
        self._build_rename_tab(notebook)
        self._build_timestamp_tab(notebook)

        output = ttk.Panedwindow(vertical, orient=tk.HORIZONTAL)
        vertical.add(output, weight=2)
        preview_frame = ttk.LabelFrame(output, text="変更プレビュー")
        output.add(preview_frame, weight=3)
        self.preview = ttk.Treeview(
            preview_frame, columns=("before", "after", "operation"), show="headings"
        )
        for column, label, width in (
            ("before", "変更前", 250),
            ("after", "変更後", 250),
            ("operation", "操作", 110),
        ):
            self.preview.heading(column, text=label, anchor=tk.W)
            self.preview.column(column, width=width, anchor=tk.W)
        preview_y = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.preview.yview)
        self.preview.configure(yscrollcommand=preview_y.set)
        self.preview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        preview_y.pack(side=tk.RIGHT, fill=tk.Y)

        result_frame = ttk.LabelFrame(output, text="実行結果・操作履歴")
        output.add(result_frame, weight=2)
        self.log = tk.Text(result_frame, height=8, wrap=tk.WORD, state=tk.DISABLED)
        log_y = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.log.yview)
        self.log.configure(yscrollcommand=log_y.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_y.pack(side=tk.RIGHT, fill=tk.Y)

        footer = ttk.Frame(container)
        footer.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(footer, textvariable=self.status_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(footer, text="プレビューをクリア", command=self._clear_preview).pack(
            side=tk.RIGHT, padx=(6, 0)
        )
        ttk.Button(footer, text="実行", command=self._execute_preview).pack(side=tk.RIGHT)

    def _build_move_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=12)
        notebook.add(tab, text="ファイル移動")
        ttk.Label(tab, text="移動先フォルダ").pack(anchor=tk.W)
        entry_row = ttk.Frame(tab)
        entry_row.pack(fill=tk.X, pady=(6, 12))
        ttk.Entry(entry_row, textvariable=self.move_destination_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(entry_row, text="参照", command=self._choose_move_destination).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        ttk.Button(tab, text="移動をプレビュー", command=self._preview_move).pack(anchor=tk.E)

    def _build_rename_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=12)
        notebook.add(tab, text="一括リネーム")
        ttk.Label(tab, text="追加する文字列").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(tab, textvariable=self.rename_text_var).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(4, 10)
        )
        ttk.Label(tab, text="追加位置").grid(row=2, column=0, sticky=tk.W)
        ttk.Combobox(
            tab,
            textvariable=self.rename_position_var,
            values=list(POSITION_LABELS),
            state="readonly",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 10))
        ttk.Checkbutton(tab, text="現在日時を追加", variable=self.use_datetime_var).grid(
            row=4, column=0, sticky=tk.W
        )
        ttk.Combobox(
            tab,
            textvariable=self.datetime_preset_var,
            values=list(DATE_FORMATS),
            state="readonly",
        ).grid(row=4, column=1, sticky="ew", padx=(6, 0))
        ttk.Label(tab, text="文字列の後ろに日時が連結されます").grid(
            row=5, column=0, columnspan=2, sticky=tk.W, pady=(4, 12)
        )
        ttk.Button(tab, text="リネームをプレビュー", command=self._preview_rename).grid(
            row=6, column=0, columnspan=2, sticky=tk.E
        )
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)

    def _build_timestamp_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=12)
        notebook.add(tab, text="タイムスタンプ")
        ttk.Label(tab, text="日時（YYYY-MM-DD HH:MM:SS）").pack(anchor=tk.W)
        ttk.Entry(tab, textvariable=self.timestamp_value_var).pack(fill=tk.X, pady=(4, 10))
        ttk.Checkbutton(tab, text="更新日時", variable=self.modify_time_var).pack(anchor=tk.W)
        ttk.Checkbutton(tab, text="アクセス日時", variable=self.access_time_var).pack(anchor=tk.W)
        creation = ttk.Checkbutton(tab, text="作成日時（Windowsのみ）", variable=self.create_time_var)
        creation.pack(anchor=tk.W)
        if os.name != "nt":
            creation.state(["disabled"])
        ttk.Button(tab, text="現在日時を入力", command=self._set_current_time).pack(
            anchor=tk.E, pady=(10, 6)
        )
        ttk.Button(tab, text="日時変更をプレビュー", command=self._preview_timestamp).pack(anchor=tk.E)

    def _choose_folder(self) -> None:
        selected = filedialog.askdirectory(
            title="管理するフォルダを選択",
            initialdir=str(self.current_folder or Path.home()),
        )
        if selected:
            self.current_folder = Path(selected)
            self.folder_var.set(str(self.current_folder))
            self.refresh_tree()

    def _choose_move_destination(self) -> None:
        selected = filedialog.askdirectory(
            title="移動先フォルダを選択",
            initialdir=str(self.current_folder or Path.home()),
        )
        if selected:
            self.move_destination_var.set(selected)

    def refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.item_paths.clear()
        if self.current_folder is None or not self.current_folder.is_dir():
            self.status_var.set("有効なフォルダを選択してください")
            return
        try:
            self._insert_directory("", self.current_folder)
            self.status_var.set(f"一覧を更新しました: {self.current_folder}")
        except OSError as exc:
            self._append_log(f"[失敗] 一覧更新: {exc}")
            self.status_var.set("一覧の更新に失敗しました")

    def _insert_directory(self, parent: str, directory: Path) -> None:
        try:
            children = sorted(directory.iterdir(), key=lambda path: (not path.is_dir(), path.name.lower()))
        except OSError as exc:
            self._append_log(f"[失敗] 読み込み: {directory} - {exc}")
            return
        for path in children:
            try:
                stat = path.stat()
                is_directory = path.is_dir()
                item = self.tree.insert(
                    parent,
                    tk.END,
                    text=path.name,
                    values=(
                        "フォルダ" if is_directory else (path.suffix.lstrip(".").upper() or "ファイル"),
                        datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        "" if is_directory else self._format_size(stat.st_size),
                    ),
                    open=False,
                )
                self.item_paths[item] = path
                if is_directory and not path.is_symlink():
                    self._insert_directory(item, path)
            except OSError as exc:
                self._append_log(f"[失敗] 情報取得: {path} - {exc}")

    def _selected_files(self) -> list[Path]:
        files = [self.item_paths[item] for item in self.tree.selection()]
        files = [path for path in files if path.is_file()]
        if not files:
            messagebox.showinfo("ファイル未選択", "ファイルを1つ以上選択してください。")
        return files

    def _preview_move(self) -> None:
        files = self._selected_files()
        if not files:
            return
        destination = Path(self.move_destination_var.get().strip())
        if not destination.is_dir():
            messagebox.showerror("移動先エラー", "有効な移動先フォルダを指定してください。")
            return
        self._show_changes(self.service.plan_move(files, destination), "移動")

    def _preview_rename(self) -> None:
        files = self._selected_files()
        if not files:
            return
        text = self.rename_text_var.get()
        if self.use_datetime_var.get():
            text += self.service.format_datetime(self.datetime_preset_var.get())
        if not text:
            messagebox.showerror("入力エラー", "追加する文字列または現在日時を指定してください。")
            return
        changes = self.service.plan_rename(
            files, text, POSITION_LABELS[self.rename_position_var.get()]
        )
        self._show_changes(changes, "リネーム")

    def _preview_timestamp(self) -> None:
        files = self._selected_files()
        if not files:
            return
        if not any((self.modify_time_var.get(), self.access_time_var.get(), self.create_time_var.get())):
            messagebox.showerror("入力エラー", "変更する日時を1つ以上選択してください。")
            return
        try:
            value = datetime.strptime(self.timestamp_value_var.get().strip(), DATETIME_INPUT_FORMAT)
        except ValueError:
            messagebox.showerror("入力エラー", "日時を YYYY-MM-DD HH:MM:SS 形式で入力してください。")
            return
        update = TimestampUpdate(
            modified=value if self.modify_time_var.get() else None,
            accessed=value if self.access_time_var.get() else None,
            created=value if self.create_time_var.get() else None,
        )
        self._clear_preview()
        self.pending_timestamp = (files, update)
        targets = ", ".join(
            label
            for enabled, label in (
                (update.modified, "更新"), (update.accessed, "アクセス"), (update.created, "作成")
            )
            if enabled is not None
        )
        after = f"{targets}: {value.strftime(DATETIME_INPUT_FORMAT)}"
        for path in files:
            self.preview.insert("", tk.END, values=(str(path), after, "日時変更"))
        self.status_var.set(f"日時変更 {len(files)}件をプレビュー中")

    def _show_changes(self, changes: list[PlannedChange], label: str) -> None:
        self._clear_preview()
        self.pending_changes = changes
        for change in changes:
            self.preview.insert(
                "", tk.END, values=(str(change.source), str(change.destination), label)
            )
        self.status_var.set(f"{label} {len(changes)}件をプレビュー中")

    def _execute_preview(self) -> None:
        count = len(self.pending_changes)
        if self.pending_timestamp:
            count = len(self.pending_timestamp[0])
        if count == 0:
            messagebox.showinfo("プレビューなし", "先に操作内容をプレビューしてください。")
            return
        if not messagebox.askyesno("実行確認", f"プレビュー中の {count} 件を実行しますか？"):
            return
        if self.pending_timestamp:
            paths, update = self.pending_timestamp
            results = self.service.update_timestamps(paths, update)
        else:
            results = self.service.apply_changes(self.pending_changes)
        successes = sum(result.success for result in results)
        for result in results:
            marker = "成功" if result.success else "失敗"
            destination = f" -> {result.destination}" if result.destination else ""
            self._append_log(f"[{marker}] {result.source}{destination}: {result.message}")
        failures = len(results) - successes
        self._clear_preview()
        self.refresh_tree()
        self.status_var.set(f"実行結果: 成功 {successes}件 / 失敗 {failures}件")
        if failures:
            messagebox.showwarning("一部失敗", "失敗した項目があります。実行結果を確認してください。")

    def _clear_preview(self) -> None:
        self.preview.delete(*self.preview.get_children())
        self.pending_changes = []
        self.pending_timestamp = None

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, f"{timestamp} {message}\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _set_current_time(self) -> None:
        self.timestamp_value_var.set(datetime.now().strftime(DATETIME_INPUT_FORMAT))

    def _restore_folder(self) -> None:
        saved = self.settings.get("last_folder")
        if saved and Path(saved).is_dir():
            self.current_folder = Path(saved)
            self.folder_var.set(saved)
            self.refresh_tree()

    def _on_close(self) -> None:
        settings = {"geometry": self.root.geometry()}
        if self.current_folder:
            settings["last_folder"] = str(self.current_folder)
        try:
            self.settings_store.save(settings)
        except OSError as exc:
            messagebox.showwarning("設定保存エラー", f"設定を保存できませんでした。\n{exc}")
        self.root.destroy()

    @staticmethod
    def _format_size(size: int) -> str:
        value = float(size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024
        return f"{size} B"


def main() -> None:
    root = tk.Tk()
    BatchFileManagerApp(root)
    root.mainloop()
