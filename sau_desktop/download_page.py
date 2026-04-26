"""下载中心页面及相关对话框."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from sau_core.services import DownloadService, ServiceError, VIDEO_DIR
from sau_desktop._shared import DenseTable, make_button, page_header


class DownloadPage(QWidget):
    refresh_requested = Signal()

    def __init__(self, download_service: DownloadService):
        super().__init__()
        self.download_service = download_service
        self.refresh_requested.connect(self.refresh)
        self.detail_dialog = None
        self.table = DenseTable(["下载时间", "下载进度", "标题", "分辨率", "文件大小"], [165, 280, 420, 100, 100])
        self.table.doubleClicked.connect(lambda _index: self.open_selected_task_detail())
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addWidget(make_button("新建下载", self.create_task, primary=True))
        action_row.addWidget(make_button("刷新", self.refresh))
        action_row.addWidget(make_button("批量删除", self.delete_selected_tasks, danger=True))
        action_row.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        layout.addWidget(page_header("下载中心", "YouTube 下载任务、进度和结果素材"))
        layout.addLayout(action_row)
        layout.addWidget(self.table, 1)
        self.refresh()

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
        tasks = self.download_service.list_youtube_tasks()
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
                self.refresh()
                QMessageBox.information(self, "删除成功", "下载任务已删除")
            except Exception as e:
                QMessageBox.warning(self, "删除失败", f"删除任务时出错: {str(e)}")

    def delete_selected_tasks(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
        task_ids = []
        task_titles = []
        for index in selected_rows:
            task = self.table.item(index.row(), 0).data(Qt.UserRole + 1)
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
        self.setMinimumSize(760, 520)

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
        self.error.setMaximumHeight(100)
        self.description = QTextEdit()
        self.description.setReadOnly(True)
        self.source_preview = self._source_preview_card()
        self.local_preview = self._media_preview_card("已下载视频")
        self.processed_preview = self._media_preview_card("处理后视频")

        summary = QFormLayout()
        summary.setLabelAlignment(Qt.AlignRight)
        summary.addRow("任务 ID", QLabel(task_id))
        summary.addRow("状态", self.status)
        summary.addRow("阶段", self.phase)
        summary.addRow("标题", self.title)
        summary.addRow("视频 URL", self.source_url)
        summary.addRow("本地文件", self.filename)
        summary.addRow("更新时间", self.updated_at)

        progress_layout = QFormLayout()
        progress_layout.setLabelAlignment(Qt.AlignRight)
        progress_layout.addRow("进度", self.progress)
        progress_layout.addRow("说明", self.progress_text)
        progress_layout.addRow("速度", self.speed)
        progress_layout.addRow("剩余时间", self.eta)

        preview_layout = QHBoxLayout()
        preview_layout.setSpacing(10)
        preview_layout.addWidget(self.source_preview["group"], 1)
        preview_layout.addWidget(self.local_preview["group"], 1)
        preview_layout.addWidget(self.processed_preview["group"], 1)

        buttons = QHBoxLayout()
        buttons.addWidget(make_button("刷新", self.refresh))
        buttons.addStretch()
        buttons.addWidget(make_button("关闭", self.close))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        layout.addLayout(summary)
        layout.addLayout(progress_layout)
        layout.addLayout(preview_layout)
        layout.addWidget(QLabel("视频描述"))
        layout.addWidget(self.description, 1)
        layout.addWidget(QLabel("失败信息"))
        layout.addWidget(self.error)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self):
        try:
            task = self.download_service.get_youtube_task(self.task_id)
        except ServiceError as exc:
            self.status.setText(str(exc))
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

    def _source_preview_card(self):
        group = QGroupBox("源视频")
        if QApplication.instance() and QApplication.platformName().lower() == "offscreen":
            body = QLabel("测试环境不加载 WebEngine")
            body.setAlignment(Qt.AlignCenter)
            body.setObjectName("PreviewPlaceholder")
            web = None
        else:
            web = QWebEngineView()
            web.setMinimumHeight(150)
            body = web
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(body, 1)
        return {"group": group, "body": body, "web": web, "source_url": None}

    def _media_preview_card(self, title: str):
        group = QGroupBox(title)
        video = QVideoWidget()
        video.setMinimumHeight(150)
        player = QMediaPlayer(self)
        audio = QAudioOutput(self)
        player.setAudioOutput(audio)
        player.setVideoOutput(video)
        placeholder = QLabel("等待视频文件")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setObjectName("PreviewPlaceholder")
        play_button = make_button("播放/暂停")
        stop_button = make_button("停止")
        play_button.setEnabled(False)
        stop_button.setEnabled(False)
        play_button.clicked.connect(lambda: self._toggle_media_player(player))
        stop_button.clicked.connect(player.stop)

        controls = QHBoxLayout()
        controls.addWidget(play_button)
        controls.addWidget(stop_button)
        controls.addStretch()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(video, 1)
        layout.addWidget(placeholder, 1)
        layout.addLayout(controls)
        video.hide()
        return {
            "group": group,
            "video": video,
            "placeholder": placeholder,
            "player": player,
            "play_button": play_button,
            "stop_button": stop_button,
            "file_path": None,
        }

    def _current_task(self) -> dict:
        return self.download_service.get_youtube_task(self.task_id)

    def _update_source_preview(self, source_url: str | None):
        if not source_url:
            if isinstance(self.source_preview["body"], QLabel):
                self.source_preview["body"].setText("等待视频链接")
            return
        if self.source_preview["source_url"] == source_url:
            return
        self.source_preview["source_url"] = source_url
        embed_url = self._youtube_embed_url(source_url)
        web = self.source_preview.get("web")
        if web:
            web.load(QUrl(embed_url or source_url))
        elif isinstance(self.source_preview["body"], QLabel):
            self.source_preview["body"].setText("源视频将在正式窗口中内嵌播放")

    def _update_media_preview(self, preview, text: str, relative_path: str | None):
        if not relative_path:
            preview["player"].stop()
            preview["file_path"] = None
            preview["video"].hide()
            preview["placeholder"].show()
            preview["placeholder"].setText(text)
            preview["play_button"].setEnabled(False)
            preview["stop_button"].setEnabled(False)
            return
        if preview["file_path"] != relative_path:
            preview["player"].stop()
            preview["file_path"] = relative_path
            preview["player"].setSource(QUrl.fromLocalFile(str(VIDEO_DIR / relative_path)))
        preview["placeholder"].hide()
        preview["video"].show()
        preview["play_button"].setEnabled(True)
        preview["stop_button"].setEnabled(True)

    def _toggle_media_player(self, player: QMediaPlayer):
        if player.playbackState() == QMediaPlayer.PlayingState:
            player.pause()
        else:
            player.play()

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
        for preview in (self.local_preview, self.processed_preview):
            preview["player"].stop()
        super().closeEvent(event)
