"""下载中心页面及相关对话框 — 选择状态栏优化."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import Qt, QUrl, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from sau_core.services import DownloadService, ServiceError, VIDEO_DIR
from sau_desktop._shared import DenseTable, EventBus, make_button, page_header, run_background
from sau_desktop.mpv_preview import MpvPreview


class DownloadPage(QWidget):
    refresh_requested = Signal()

    def __init__(self, download_service: DownloadService, event_bus: EventBus):
        super().__init__()
        self.download_service = download_service
        self.event_bus = event_bus
        self._refresh_running = False
        self._refresh_again = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(500)
        self._refresh_timer.timeout.connect(self.refresh)
        self.refresh_requested.connect(self.schedule_refresh)
        self.detail_dialog = None
        # 下载中心表格本身没有 ID 列，已合理
        self.table = DenseTable(["下载时间", "下载进度", "标题", "分辨率", "文件大小"], [165, 280, 420, 100, 100])
        self.table.doubleClicked.connect(lambda _: self.open_selected_task_detail())
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        # P2: 选择状态栏
        self.selection_label = QLabel("")
        self.selection_label.setObjectName("SelectionInfo")

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addWidget(make_button("新建下载", self.create_task, primary=True))
        action_row.addWidget(make_button("刷新", self.refresh))
        action_row.addWidget(make_button("批量删除", self.delete_selected_tasks, danger=True))
        action_row.addStretch()
        action_row.addWidget(self.selection_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)
        layout.addWidget(page_header("下载中心", "YouTube 下载任务、进度和结果素材"))
        layout.addLayout(action_row)
        layout.addWidget(self.table, 1)

        # P2: 连接选择变化信号
        self.table.selection_changed.connect(self._update_selection_info)

        self.event_bus.materials_changed.connect(self.schedule_refresh)

    def _update_selection_info(self, count: int):
        if count > 0:
            self.selection_label.setText(f"已选 {count} 项")
        else:
            self.selection_label.setText("")

    def create_task(self):
        dialog = CreateDownloadDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        url, download_subtitles = dialog.values()
        try:
            task_id = self.download_service.create_youtube_download_task(
                url,
                download_subtitles,
                callback=lambda _: self.refresh_requested.emit(),
            )
            self.refresh()
            self.open_task_detail(task_id)
        except ServiceError as exc:
            QMessageBox.warning(self, "下载失败", str(exc))

    def open_task_detail(self, task_id: str):
        if self.detail_dialog:
            self.detail_dialog.close()
        self.detail_dialog = DownloadTaskDetailDialog(self.download_service, task_id, self)
        self.detail_dialog.show()
        self.detail_dialog.raise_()
        self.detail_dialog.activateWindow()

    def refresh(self):
        if self._refresh_running:
            self._refresh_again = True
            return
        self._refresh_running = True
        run_background(self, self._fetch_tasks, on_done=self._on_tasks_loaded, on_error=self._on_tasks_load_failed)

    def schedule_refresh(self):
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def _fetch_tasks(self):
        return self.download_service.list_youtube_tasks()

    def _on_tasks_loaded(self, tasks):
        self._refresh_running = False
        self._apply_tasks(tasks)
        if self._refresh_again:
            self._refresh_again = False
            self.schedule_refresh()

    def _on_tasks_load_failed(self, message: str):
        self._refresh_running = False
        if self._refresh_again:
            self._refresh_again = False
            self.schedule_refresh()
        QMessageBox.critical(self, "错误", message)

    def _apply_tasks(self, tasks):
        self.table.set_rows(
            [
                [
                    task.get("createdAt") or task.get("updatedAt"),
                    self._progress_text(task),
                    task.get("videoTitleZh") or task.get("videoTitle") or task.get("sourceUrl"),
                    task.get("resolution") or "-",
                    self._file_size_text(task),
                ]
                for task in tasks
            ],
            payloads=tasks,
        )
        if self.detail_dialog and self.detail_dialog.isVisible():
            self.detail_dialog.refresh()

    def selected_task(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0):
            return None
        return self.table.item(row, 0).data(Qt.UserRole + 1)

    def open_selected_task_detail(self):
        task = self.selected_task()
        if task and task.get("taskId"):
            self.open_task_detail(task["taskId"])

    def show_context_menu(self, position):
        row = self.table.rowAt(position.y())
        if row >= 0:
            self.table.selectRow(row)
        task = self.selected_task()
        if not task:
            return
        menu = QMenu(self)
        detail_action = menu.addAction("查看详情")
        delete_action = menu.addAction("删除")
        action = menu.exec(self.table.viewport().mapToGlobal(position))
        if action == detail_action:
            self.open_selected_task_detail()
        elif action == delete_action:
            self.delete_selected_task()

    def delete_selected_task(self):
        task = self.selected_task()
        if not task:
            return
        task_id = task.get("taskId")
        if not task_id:
            return
        reply = QMessageBox.question(
            self,
            "删除任务",
            f"确定要删除此下载任务吗？\n{task.get('videoTitleZh') or task.get('videoTitle') or '未知视频'}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                self.download_service.delete_youtube_task(task_id)
                self.event_bus.materials_changed.emit()
                self.refresh()
                QMessageBox.information(self, "删除成功", "下载任务已删除")
            except Exception as e:
                QMessageBox.warning(self, "删除失败", f"删除任务时出错: {str(e)}")

    def delete_selected_tasks(self):
        checked = self.table.checked_rows()
        if not checked:
            return
        task_ids = []
        task_titles = []
        for row in checked:
            task = self.table.item(row, 0).data(Qt.UserRole + 1)
            task_id = task.get("taskId")
            if task_id:
                task_ids.append(task_id)
                task_titles.append(task.get('videoTitleZh') or task.get('videoTitle') or '未知视频')
        if not task_ids:
            return
        reply = QMessageBox.question(
            self,
            "批量删除",
            f"确定要删除这 {len(task_ids)} 个下载任务吗？\n\n{chr(10).join(task_titles[:3])}{'...' if len(task_titles) > 3 else ''}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                result = self.download_service.delete_youtube_tasks(task_ids)
                self.event_bus.materials_changed.emit()
                self.refresh()
                QMessageBox.information(self, "删除成功", f"成功删除 {len(result.get('deleted', []))} 个任务")
            except Exception as e:
                QMessageBox.warning(self, "删除失败", f"删除任务时出错: {str(e)}")

    def _progress_text(self, task: dict) -> str:
        percent = task.get("progressPercent")
        if isinstance(percent, (int, float)):
            prefix = f"{int(percent)}%"
        elif task.get("status") == "success":
            prefix = "100%"
        else:
            prefix = "-"
        detail = task.get("processingProgressText") or task.get("progressText") or task.get("status") or ""
        return f"{prefix}  {detail}".strip()

    def _file_size_text(self, task: dict) -> str:
        size = task.get("fileSize")
        if isinstance(size, (int, float)):
            return f"{size:.2f} MB"
        total_bytes = task.get("totalBytes")
        if isinstance(total_bytes, (int, float)) and total_bytes > 0:
            return f"{total_bytes / 1024 / 1024:.2f} MB"
        return "-"


class CreateDownloadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建 YouTube 下载")
        self.setMinimumWidth(520)
        self.url = QLineEdit()
        self.url.setPlaceholderText("请输入单个 YouTube 视频链接")
        self.subtitles = QCheckBox("下载字幕")
        self.subtitles.setChecked(True)
        tip = QLabel("下载会自动提取元数据，并将标题翻译为中文后保存。")
        tip.setObjectName("PageSubtitle")

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow("视频链接", self.url)
        form.addRow("字幕", self.subtitles)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("开始下载")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        layout.addLayout(form)
        layout.addWidget(tip)
        layout.addWidget(buttons)

    def accept(self):
        if not self.url.text().strip():
            QMessageBox.warning(self, "新建下载", "请输入 YouTube 视频链接")
            return
        super().accept()

    def values(self) -> tuple[str, bool]:
        return self.url.text().strip(), self.subtitles.isChecked()


class DownloadTaskDetailDialog(QDialog):
    def __init__(self, download_service: DownloadService, task_id: str, parent=None):
        super().__init__(parent)
        self.download_service = download_service
        self.task_id = task_id
        self.setWindowTitle("下载详情")
        self.setMinimumSize(1000, 580)

        # --- Left: info ---
        self.status = QLabel()
        self.phase = QLabel()
        self.title = QLabel()
        self.source_url = QLabel()
        self.source_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.filename = QLabel()
        self.updated_at = QLabel()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress_text = QLabel()
        self.speed = QLabel()
        self.eta = QLabel()
        self.error = QTextEdit()
        self.error.setReadOnly(True)
        self.error.setMaximumHeight(80)
        self.description = QTextEdit()
        self.description.setReadOnly(True)

        summary = QFormLayout()
        summary.setLabelAlignment(Qt.AlignRight)
        summary.addRow("任务 ID", QLabel(task_id))
        summary.addRow("状态", self.status)
        summary.addRow("阶段", self.phase)
        summary.addRow("标题", self.title)
        summary.addRow("视频 URL", self.source_url)
        summary.addRow("本地文件", self.filename)
        summary.addRow("更新时间", self.updated_at)

        progress_form = QFormLayout()
        progress_form.setLabelAlignment(Qt.AlignRight)
        progress_form.addRow("进度", self.progress)
        progress_form.addRow("说明", self.progress_text)
        progress_form.addRow("速度", self.speed)
        progress_form.addRow("剩余时间", self.eta)

        left_layout = QVBoxLayout()
        left_layout.setSpacing(8)
        left_layout.addLayout(summary)
        left_layout.addLayout(progress_form)
        left_layout.addWidget(QLabel("视频描述"))
        left_layout.addWidget(self.description, 1)
        left_layout.addWidget(QLabel("失败信息"))
        left_layout.addWidget(self.error)

        # --- Right: video previews in tabs ---
        self.source_preview = self._source_preview_card()
        self.local_preview = self._media_preview_card()
        self.processed_preview = self._media_preview_card()

        preview_tabs = QTabWidget()
        preview_tabs.addTab(self.source_preview["widget"], "源视频")
        preview_tabs.addTab(self.local_preview["widget"], "已下载视频")
        preview_tabs.addTab(self.processed_preview["widget"], "处理后视频")

        # --- Buttons ---
        buttons = QHBoxLayout()
        buttons.addWidget(make_button("刷新", self.refresh))
        buttons.addStretch()
        buttons.addWidget(make_button("关闭", self.close))

        # --- Main layout: left 1 : right 1 ---
        main_split = QHBoxLayout()
        main_split.setSpacing(12)
        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        main_split.addWidget(left_widget, 1)
        main_split.addWidget(preview_tabs, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        layout.addLayout(main_split, 1)
        layout.addLayout(buttons)

        # Auto-refresh timer for active tasks (downloading / processing)
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.setInterval(1500)
        self._auto_refresh_timer.timeout.connect(self.refresh)
        self._auto_refresh_timer.start()
        self.refresh()

    def refresh(self):
        try:
            task = self.download_service.get_youtube_task(self.task_id)
        except ServiceError as exc:
            self.status.setText(str(exc))
            self._auto_refresh_timer.stop()
            return
        title = task.get("videoTitleZh") or task.get("videoTitle") or "-"
        progress_percent = task.get("progressPercent")
        if not isinstance(progress_percent, (int, float)):
            progress_percent = 100 if task.get("status") == "success" else 0

        self.status.setText(task.get("status") or "-")
        self.phase.setText(task.get("phase") or "-")
        self.title.setText(title)
        self.source_url.setText(task.get("sourceUrl") or "-")
        self.filename.setText(task.get("filename") or "-")
        self.updated_at.setText(task.get("updatedAt") or "-")
        self.progress.setValue(max(0, min(100, int(progress_percent))))
        self.progress_text.setText(task.get("progressText") or "-")
        self.speed.setText(task.get("speedText") or "-")
        self.eta.setText(task.get("etaText") or "-")
        self.description.setPlainText(task.get("videoDescription") or "")
        self.error.setPlainText(task.get("errorDetail") or task.get("errorMessage") or "")
        self._update_source_preview(task.get("sourceUrl"))
        self._update_media_preview(
            self.local_preview,
            task.get("filename") or "等待下载完成",
            task.get("filePath"),
        )
        processing_text = task.get("processingProgressText") or "等待视频处理"
        if task.get("processedFilePath"):
            processing_text = task.get("processedFilename") or task.get("processedFilePath")
        self._update_media_preview(
            self.processed_preview,
            processing_text,
            task.get("processedFilePath"),
        )

        # Stop auto-refresh once the task reaches a terminal state
        task_status = task.get("status")
        if task_status in ("success", "failed"):
            self._auto_refresh_timer.stop()

    def _source_preview_card(self):
        widget = QWidget()
        placeholder = QLabel("点击加载源视频预览")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setObjectName("PreviewPlaceholder")
        load_button = make_button("加载预览")
        load_button.setEnabled(False)

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.addWidget(placeholder, 1)
        layout.addWidget(load_button)

        return {
            "widget": widget,
            "placeholder": placeholder,
            "load_button": load_button,
            "web": None,
            "source_url": None,
        }

    def _lazy_load_web_engine(self):
        """Lazily create QWebEngineView only when needed."""
        preview = self.source_preview
        if preview["web"] is not None:
            return
        if QApplication.instance() and QApplication.platformName().lower() == "offscreen":
            preview["placeholder"].setText("测试环境不加载 WebEngine")
            return
        from PySide6.QtWebEngineWidgets import QWebEngineView
        web = QWebEngineView()
        layout = preview["widget"].layout()
        layout.removeWidget(preview["placeholder"])
        preview["placeholder"].deleteLater()
        layout.insertWidget(0, web, 1)
        preview["web"] = web

    def _media_preview_card(self):
        widget = QWidget()
        preview_widget = MpvPreview(self)
        play_button = make_button("播放/暂停")
        stop_button = make_button("停止")
        play_button.setEnabled(False)
        stop_button.setEnabled(False)

        controls = QHBoxLayout()
        controls.addWidget(play_button)
        controls.addWidget(stop_button)
        controls.addStretch()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.addWidget(preview_widget, 1)
        layout.addLayout(controls)
        preview = {
            "widget": widget,
            "preview": preview_widget,
            "play_button": play_button,
            "stop_button": stop_button,
            "file_path": None,
        }
        play_button.clicked.connect(lambda: self._toggle_media_preview(preview))
        stop_button.clicked.connect(preview_widget.stop)
        return preview

    def _current_task(self) -> dict:
        return self.download_service.get_youtube_task(self.task_id)

    def _update_source_preview(self, source_url: str | None):
        preview = self.source_preview
        if not source_url:
            preview["placeholder"].setText("等待视频链接")
            preview["load_button"].setEnabled(False)
            return
        if preview["source_url"] == source_url:
            return
        preview["source_url"] = source_url
        embed_url = self._youtube_embed_url(source_url)

        # Lazy load: create WebEngine on first URL
        self._lazy_load_web_engine()
        web = preview.get("web")
        if web:
            web.load(QUrl(embed_url or source_url))
            preview["load_button"].setVisible(False)
        else:
            preview["placeholder"].setText("源视频将在正式窗口中内嵌播放")

    def _update_media_preview(self, preview, text: str, relative_path: str | None):
        if not relative_path:
            preview["file_path"] = None
            preview["preview"].set_placeholder(text)
            preview["play_button"].setEnabled(False)
            preview["stop_button"].setEnabled(False)
            return
        if preview["file_path"] != relative_path:
            preview["file_path"] = relative_path
            preview["preview"].set_source(VIDEO_DIR / relative_path)
        preview["play_button"].setEnabled(True)
        preview["stop_button"].setEnabled(True)

    def _toggle_media_preview(self, preview):
        preview["preview"].toggle_playback()

    def _youtube_embed_url(self, source_url: str) -> str:
        parsed = urlparse(source_url)
        video_id = ""
        if "youtu.be" in parsed.netloc:
            video_id = parsed.path.strip("/").split("/", 1)[0]
        else:
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        if not video_id:
            return ""
        return f"https://www.youtube.com/embed/{video_id}"

    def closeEvent(self, event):
        self._auto_refresh_timer.stop()
        for preview in (self.local_preview, self.processed_preview):
            preview["preview"].close()
        # Clean up WebEngine if it was created
        web = self.source_preview.get("web")
        if web:
            web.stop()
            web.setUrl(QUrl(""))
        super().closeEvent(event)
