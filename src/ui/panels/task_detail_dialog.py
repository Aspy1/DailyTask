"""作业详情弹窗：**备注（纯文本）+ 附件（添加 / 打开 / 删除）**。

三个必须守住的顺序 / 边界：

1. **备注是纯文本**：`QPlainTextEdit`（不是 `QTextEdit`）—— 粘贴带格式的内容时
   不会把 HTML 存进 `tasks.json`；长度上限 `MAX_NOTES`（超出即截断，不静默丢内容）。
2. **附件"先提交索引、再删文件"**：删除只是把条目移出内存列表并记进 `_removed`；
   真正的 `unlink` 发生在 `model.save()` 返回 `True` 之后（`AttachmentStore.remove`
   的 `commit` 契约）。`save()` 失败 → 弹错、**一个文件都不删**。
3. **打开文件走 `QDesktopServices`**：绝不拼 `subprocess`/`explorer` 字符串
   （文件名里的空格、引号、中文都会变成命令注入面）。文件不在了 → 只提示，不抛异常。
"""

import copy
import logging
from datetime import date
from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.services.attachments import (
    MAX_FILE_BYTES,
    MAX_FILES_PER_TASK,
    AttachmentError,
    human_size,
)
from src.services.data_manager import DataManager
from src.ui.styles.theme import (
    CONTROLS,
    LAYOUT,
    RADIUS,
    SIZE_BODY_L,
    SIZE_CAPTION,
    SPACING,
    btn_ghost_qss,
    get_colors,
)
from src.ui.widgets.dialog_shell import DialogShell, action_row
from src.ui.widgets.rounded_button import RoundedButton

logger = logging.getLogger(__name__)

# 备注上限（字符数）。纯文本，按字符计 —— 中文一个字算一个。
MAX_NOTES = 20000

# 保存失败时要**原样改回**的内存字段：`TaskModel.update()` 会就地改任务并盖
# `updated_at`，不还原的话内存就领先磁盘 —— 退出时 `flush_on_exit()` 会判定
# "磁盘被外部改过"，把这份没落盘的改动刷成冲突副本（用户只看到"保存失败"）。
_ROLLBACK_KEYS = ("notes", "attachments", "updated_at")

# 服务层的错误码 → i18n 键（服务层不写中文，文案只存在于语言包）
_ERROR_KEYS = {
    "too_large": "dialog.task.msg_too_large",
    "too_many": "dialog.task.msg_too_many",
    "rejected": "dialog.task.msg_rejected",
    "unsafe_path": "dialog.task.msg_rejected",
}


def ask_open_file(parent: QWidget | None) -> str:
    """选一个文件（包装 `QFileDialog`，测试可替换）。"""
    path, _selected_filter = QFileDialog.getOpenFileName(
        parent, tr("dialog.task.btn_add_file"), "", tr("dialog.task.file_filter"))
    return path


def open_path(path: Path) -> bool:
    """用系统默认程序打开（`QDesktopServices`，不经过 shell）。"""
    return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))


def add_error_text(exc: AttachmentError) -> str:
    """把附件错误映射成用户能读的文案。"""
    key = _ERROR_KEYS.get(getattr(exc, "code", ""), "dialog.task.msg_add_failed")
    if key == "dialog.task.msg_too_large":
        return tr(key, mb=MAX_FILE_BYTES // (1024 * 1024))
    if key == "dialog.task.msg_too_many":
        return tr(key, n=MAX_FILES_PER_TASK)
    return tr(key)


def format_added_at(added_at: str) -> str:
    """`added_at` ISO 串 → `YYYY-MM-DD`（解析不了就原样截断，不抛异常）。"""
    raw = str(added_at or "")
    if not raw:
        return ""
    try:
        return date.fromisoformat(raw[:10]).isoformat()
    except ValueError:
        return raw[:10]


class TaskDetailDialog(DialogShell):
    """作业详情：改备注 + 管附件。`exec()` 返回 1 = 已保存。"""

    saved = Signal()

    def __init__(self, dm: DataManager, task: dict, parent=None) -> None:
        title = str(task.get("title") or "")
        super().__init__(parent, title=tr("dialog.task.title", name=title),
                         min_width=LAYOUT["dialog_width_lg"], buttons=False)
        self._dm = dm
        self._task = task
        self._task_id = str(task.get("id") or "")
        # 内存副本：所有改动先落这里，点「保存」才一次性写进 model
        self._entries: list[dict] = [dict(e) for e in (task.get("attachments") or [])
                                     if isinstance(e, dict) and e.get("stored_name")]
        # 打开时的**索引快照**：清理只针对"最终没人引用"的实体（审计 P1 的差集依据）
        self._original_entries: list[dict] = [dict(e) for e in self._entries]
        self._removed: list[str] = []      # 曾经移出列表（只用于状态提示，不再决定删谁）
        self._added: list[str] = []        # 本次新增（取消 / 保存失败时要回滚）
        self._build()
        self.add_action_row(action_row(
            tr("dialog.task.btn_save"), self._on_save, on_cancel=self.reject))

    # ── 构建 ────────────────────────────────────────────────

    def _build(self) -> None:
        c = get_colors()
        self.body.addWidget(self._make_header())
        self.body.addWidget(self._make_section_title(tr("dialog.task.label_notes")))

        self._notes = QPlainTextEdit()
        self._notes.setObjectName("taskNotesEdit")
        self._notes.setPlainText(str(self._task.get("notes") or ""))
        self._notes.setPlaceholderText(tr("dialog.task.notes_placeholder"))
        self._notes.setTabChangesFocus(True)
        self._notes.setFrameShape(QFrame.Shape.NoFrame)
        self._notes.setMinimumHeight(LAYOUT["api_test_output_max_height"])
        self._notes.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {c['input_bg']}; color: {c['fg_primary']};"
            f" border: 1px solid {c['border']}; border-radius: {RADIUS['radius_md']}px;"
            f" padding: {SPACING['spacing_sm']}px; }}")
        self._notes.textChanged.connect(self._on_notes_changed)
        self.body.addWidget(self._notes)

        self._notes_hint = QLabel()
        self._notes_hint.setObjectName("taskNotesHint")
        self._notes_hint.setStyleSheet(
            f"color: {c['fg_hint']}; font-size: {SIZE_CAPTION}px;")
        self.body.addWidget(self._notes_hint)

        self.body.addWidget(self._make_attachments_header())

        holder = QWidget()
        holder.setObjectName("taskAttachmentList")
        holder.setStyleSheet("QWidget#taskAttachmentList { background: transparent; }")
        self._rows_layout = QVBoxLayout(holder)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(SPACING["spacing_xs"])
        self.body.addWidget(holder)

        self._status = QLabel()
        self._status.setObjectName("taskDetailStatus")
        self._status.setStyleSheet(f"color: {c['fg_hint']}; font-size: {SIZE_CAPTION}px;")
        self.body.addWidget(self._status)
        self.body.addStretch()

        self._on_notes_changed()
        self._rebuild_rows()

    def _make_header(self) -> QWidget:
        """顶部只放**元信息**（课程 / 截止）—— 标题已在窗口标题栏（Q-H10）。"""
        c = get_colors()
        head = QWidget()
        head.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(head)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        title = QLabel(str(self._task.get("title") or ""))
        title.setObjectName("taskDetailTitle")
        title.setWordWrap(True)
        title.setStyleSheet(
            f"color: {c['fg_primary']}; font-size: {SIZE_BODY_L}px; font-weight: 600;")
        lay.addWidget(title)

        meta = QLabel(self._meta_text())
        meta.setObjectName("taskDetailMeta")
        meta.setWordWrap(True)
        meta.setStyleSheet(f"color: {c['fg_hint']}; font-size: {SIZE_CAPTION}px;")
        lay.addWidget(meta)
        return head

    def _meta_text(self) -> str:
        course = str(self._task.get("course_name") or "—")
        due = str(self._task.get("due_date") or "")
        due_display = due[:16].replace("T", " ") if due and due != "None" else "—"
        return tr("dialog.task.meta_line", course=course, due=due_display)

    @staticmethod
    def _make_section_title(text: str) -> QLabel:
        c = get_colors()
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {c['fg_secondary']}; font-size: {SIZE_CAPTION}px; font-weight: 600;")
        return label

    def _make_attachments_header(self) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(SPACING["spacing_sm"])
        lay.addWidget(self._make_section_title(tr("dialog.task.label_attachments")))
        lay.addStretch()

        self._add_btn = RoundedButton(tr("dialog.task.btn_add_file"))
        self._add_btn.setObjectName("taskAddAttachment")
        self._add_btn.setStyleSheet(btn_ghost_qss())
        self._add_btn.setFixedHeight(CONTROLS["button_height_sm"])
        self._add_btn.clicked.connect(self._on_add_clicked)
        lay.addWidget(self._add_btn)
        return row

    # ── 备注 ────────────────────────────────────────────────

    def _on_notes_changed(self) -> None:
        """超出上限就截断（**不静默**：提示行说明已截断）。"""
        text = self._notes.toPlainText()
        if len(text) > MAX_NOTES:
            self._notes.blockSignals(True)
            self._notes.setPlainText(text[:MAX_NOTES])
            cursor = self._notes.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._notes.setTextCursor(cursor)
            self._notes.blockSignals(False)
            text = text[:MAX_NOTES]
            self._notes_hint.setText(tr("dialog.task.notes_truncated", n=MAX_NOTES))
            return
        self._notes_hint.setText(tr("dialog.task.notes_count", n=len(text), max=MAX_NOTES))

    def notes_text(self) -> str:
        """当前备注（已按上限截断）。"""
        return self._notes.toPlainText()[:MAX_NOTES]

    # ── 附件行 ──────────────────────────────────────────────

    def _rebuild_rows(self) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not self._entries:
            empty = QLabel(tr("dialog.task.empty_attachments"))
            empty.setObjectName("taskAttachmentEmpty")
            empty.setStyleSheet(
                f"color: {get_colors()['fg_hint']}; font-size: {SIZE_CAPTION}px;")
            self._rows_layout.addWidget(empty)
            return
        for entry in self._entries:
            self._rows_layout.addWidget(self._make_row(entry))

    def _make_row(self, entry: dict) -> QWidget:
        c = get_colors()
        row = QWidget()
        row.setObjectName("taskAttachmentRow")
        row.setStyleSheet(
            f"QWidget#taskAttachmentRow {{ background-color: {c['bg_elevated']};"
            f" border-radius: {RADIUS['radius_md']}px; }}")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(SPACING["spacing_sm"], SPACING["spacing_xs"],
                               SPACING["spacing_sm"], SPACING["spacing_xs"])
        lay.setSpacing(SPACING["spacing_sm"])

        name = QLabel(str(entry.get("name") or entry.get("stored_name") or ""))
        name.setObjectName("taskAttachmentName")
        name.setWordWrap(True)
        lay.addWidget(name, 1)

        meta = QLabel(self._entry_meta(entry))
        meta.setObjectName("taskAttachmentMeta")
        meta.setStyleSheet(f"color: {c['fg_hint']}; font-size: {SIZE_CAPTION}px;")
        lay.addWidget(meta)

        open_btn = RoundedButton(tr("dialog.task.btn_open"))
        open_btn.setObjectName("taskAttachmentOpen")
        open_btn.setStyleSheet(btn_ghost_qss())
        open_btn.setFixedHeight(CONTROLS["button_height_sm"])
        open_btn.clicked.connect(lambda _checked=False, e=entry: self._on_open(e))
        lay.addWidget(open_btn)

        remove_btn = RoundedButton(tr("dialog.task.btn_remove"))
        remove_btn.setObjectName("taskAttachmentRemove")
        remove_btn.setStyleSheet(btn_ghost_qss())
        remove_btn.setFixedHeight(CONTROLS["button_height_sm"])
        remove_btn.clicked.connect(lambda _checked=False, e=entry: self._on_remove(e))
        lay.addWidget(remove_btn)
        return row

    def _entry_meta(self, entry: dict) -> str:
        """大小 · 添加日期（文件不在了 → 追加"已丢失"）。"""
        size = human_size(int(entry.get("size") or 0))
        added = format_added_at(str(entry.get("added_at") or ""))
        text = tr("dialog.task.attachment_meta", size=size, date=added) if added \
            else size
        if self._dm.attachments.resolve(self._task_id,
                                        str(entry.get("stored_name") or "")) is None:
            text = f"{text} · {tr('dialog.task.missing_file')}"
        return text

    def _on_open(self, entry: dict) -> None:
        stored = str(entry.get("stored_name") or "")
        path = self._dm.attachments.resolve(self._task_id, stored)
        if path is None:
            QMessageBox.warning(self, tr("dialog.task.missing_title"),
                                tr("dialog.task.msg_missing", name=str(entry.get("name") or stored)))
            return
        if not open_path(path):
            QMessageBox.warning(self, tr("dialog.task.missing_title"),
                                tr("dialog.task.msg_open_failed", name=str(entry.get("name") or stored)))

    def _on_remove(self, entry: dict) -> None:
        """只从内存列表移除并记进 `_removed`；文件在保存成功后才删。"""
        stored = str(entry.get("stored_name") or "")
        self._entries = [e for e in self._entries
                         if str(e.get("stored_name") or "") != stored]
        if stored and stored not in self._removed:
            self._removed.append(stored)
        self._status.setText(tr("dialog.task.pending_remove", name=str(entry.get("name") or stored)))
        self._rebuild_rows()

    # ── 新增 ────────────────────────────────────────────────

    def _on_add_clicked(self) -> None:
        path = ask_open_file(self)
        if path:
            self._add_path(path)

    def _add_path(self, path: str | Path) -> bool:
        """把文件加进列表；失败弹提示并返回 False（**测试直接调它**）。"""
        try:
            entry = self._dm.attachments.add(self._task_id, path, self._entries)
        except AttachmentError as exc:
            logger.info("添加附件被拒（%s）：%s", getattr(exc, "code", "?"), exc)
            QMessageBox.warning(self, tr("dialog.task.add_failed_title"),
                                add_error_text(exc))
            return False
        stored = str(entry.get("stored_name") or "")
        existing = {str(e.get("stored_name") or "") for e in self._entries}
        if stored in existing:
            self._status.setText(tr("dialog.task.duplicate", name=str(entry.get("name") or stored)))
            return True
        self._entries.append(dict(entry))
        if stored and stored not in self._initial_names():
            # 只有**真正新落盘**的才进回滚名单：删掉再加回同内容会复用同一个
            # `stored_name`，那是打开时就在的实体 —— 回滚它等于删掉既有附件。
            self._added.append(stored)
        self._status.setText(tr("dialog.task.added", name=str(entry.get("name") or stored)))
        self._rebuild_rows()
        return True

    # ── 保存 / 取消 ─────────────────────────────────────────

    def _find_task(self) -> dict | None:
        """按 id 取模型里**那一份**任务 dict（`self._task` 可能是调用方给的副本）。"""
        return next((t for t in self._dm.tasks.tasks
                     if str(t.get("id") or "") == self._task_id), None)

    @staticmethod
    def _snapshot_task(task: dict) -> dict[str, tuple[bool, object]]:
        """记下待回滚字段的**存在性 + 值**（深拷贝；原来没有的键也必须原样缺席）。"""
        return {key: (key in task, copy.deepcopy(task.get(key)))
                for key in _ROLLBACK_KEYS}

    @staticmethod
    def _restore_task(task: dict | None,
                      snapshot: dict[str, tuple[bool, object]] | None) -> None:
        """保存失败 → 内存改回保存前（**只动内存**，不碰任何文件）。

        原来**没有**的键要删掉，不能留一个空壳：`tasks.json` 有没有这个键会改变
        内容指纹，也会让"老数据（无 `attachments` 键）"在内存里悄悄升级成新 schema。
        """
        if task is None or snapshot is None:
            return
        for key, (existed, value) in snapshot.items():
            if existed:
                task[key] = copy.deepcopy(value)
            else:
                task.pop(key, None)

    def _on_save(self) -> None:
        """先写索引（model.save），成功后才删文件；失败 → 弹错、文件一个都不删、内存改回原样。

        **待删按最终引用重算（审计 2026-11-21 P1）**：原来记的是"点过删除"的名单，
        而"删掉再加回同内容"会让名单和最终列表脱节 —— 索引里留着一条、
        实体却被清理掉了。现在一律用 `初始 ∪ 新增 − 最终` 的差集，名单不再是决策依据。
        """
        changes = {
            "notes": self.notes_text(),
            "attachments": [dict(e) for e in self._entries],
        }
        # 快照必须在 `update()` **之前**：它就地改内存里的任务，`save()` 再失败的话
        # 内存就比磁盘多出一份改动，退出时会被 `flush_on_exit()` 刷成冲突副本。
        target = self._find_task()
        snapshot = self._snapshot_task(target) if target is not None else None
        if not self._dm.tasks.update(self._task_id, changes):
            self._rollback_added()
            QMessageBox.warning(self, tr("dialog.task.save_failed_title"),
                                tr("dialog.task.msg_task_missing"))
            return
        if not self._dm.tasks.save():
            # ⚠ 这里**不能**删任何文件：索引没落盘，删了就出现"JSON 还指着但文件没了"
            self._restore_task(target, snapshot)
            self._rollback_added()
            QMessageBox.warning(self, tr("dialog.task.save_failed_title"),
                                tr("dialog.task.msg_save_failed"))
            return
        self._commit_removals()
        self._added.clear()
        self._dm.data_changed.emit("task")
        self.saved.emit()
        self.accept()

    def _commit_removals(self) -> None:
        """索引已提交 → 现在才删文件；**只删最终没人引用的**（失败只记日志）。"""
        referenced = {str(e.get("stored_name") or "") for e in self._entries}
        doomed = [stored for stored in self._initial_names() | set(self._added)
                  if stored and stored not in referenced]
        failed = [stored for stored in doomed
                  if not self._dm.attachments.discard(self._task_id, stored)]
        self._removed.clear()
        if failed:
            # 索引已经提交成功（条目已不在列表里），这里只影响磁盘上的残留文件
            self._status.setText(tr("dialog.task.remove_failed", n=len(failed)))
            logger.warning("附件文件未能删除（索引已提交）：%s → %s",
                           self._task_id, "、".join(failed))

    def _initial_names(self) -> set[str]:
        """打开弹窗时**磁盘索引**里的附件名（不是"点过删除"的名单）。"""
        return {str(e.get("stored_name") or "") for e in self._original_entries
                if isinstance(e, dict) and e.get("stored_name")}

    def reject(self) -> None:
        """取消 / 关窗：回滚本次新增的**文件副本**（索引没提交，文件也没有引用）。"""
        self._rollback_added()
        super().reject()

    def _rollback_added(self) -> None:
        """回滚**本次新增**的文件副本；既有实体一个都不动（哪怕点过"移除"）。

        "移除了一个既有附件、然后保存失败"时，索引还是原来的那份 ——
        文件必须跟着索引留着，否则重开就是"条目在、文件没了"。
        """
        for stored in self._added:
            self._dm.attachments.discard(self._task_id, stored)
        removed = set(self._added)
        self._entries = [entry for entry in self._entries if entry.get("stored_name") not in removed]
        self._added.clear()
        if removed:
            self._rebuild_rows()
