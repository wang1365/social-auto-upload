"""发布中心页面 — 上下布局 + 隐藏ID + 可折叠日志."""

from __future__ import annotations

from PySide6.QtCore import Qt, QSignalBlocker, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QLabel,
)

from sau_core.services import AccountService, MaterialService, PublishService
from sau_desktop._shared import (
    DenseTable, EventBus, make_button, page_header, run_background,
    CollapsibleSection, reveal_file_in_folder,
)


class PublishPage(QWidget):
    def __init__(self, material_service: MaterialService, account_service: AccountService, publish_service: PublishService, event_bus: EventBus):
        super().__init__()
        self.material_service = material_service
        self.account_service = account_service
        self.publish_service = publish_service
        self.event_bus = event_bus
        self._is_publishing = False
        self._account_publish_results: dict[tuple, str] = {}
        self._all_accounts: list[dict] = []
        self._remembered_account_keys: set[str] = set()
        self._remembered_platform_type = None
        self._title_auto_generated = False

        # P0: 隐藏 ID 列和路径列，用户只需看文件名
        self.materials = DenseTable(["文件名", "来源"], [360, 120])
        self.materials.setContextMenuPolicy(Qt.CustomContextMenu)
        self.materials.customContextMenuRequested.connect(self.show_material_context_menu)
        # P0: 隐藏 ID 列，增加状态列便于识别可用账号
        self.accounts = DenseTable(["平台", "用户名", "状态", "发布结果"], [100, 160, 80, 220])
        self.materials.setFixedHeight(190)
        self.accounts.setFixedHeight(190)
        self.platform_filter = QComboBox()
        self.platform_filter.currentIndexChanged.connect(self._on_platform_filter_changed)

        self.title = QLineEdit()
        self.title.setPlaceholderText("发布标题")
        self.title.textEdited.connect(self._on_title_edited)
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("话题，逗号分隔")
        self.topic_preset = QComboBox()
        self.topic_preset.currentIndexChanged.connect(self._apply_topic_preset)
        topic_widget = QWidget()
        topic_row = QHBoxLayout(topic_widget)
        topic_row.setContentsMargins(0, 0, 0, 0)
        topic_row.setSpacing(8)
        topic_row.addWidget(self.tags, 2)
        topic_row.addWidget(self.topic_preset, 1)

        # P2: 日志区域默认折叠
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(140)
        self.log_section = CollapsibleSection("运行日志", self.log, expanded=False)
        self.log_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.publish_status = QLabel("")
        self.publish_status.setObjectName("SelectionInfo")
        self.publish_loading = QProgressBar()
        self.publish_loading.setRange(0, 0)
        self.publish_loading.setMaximumWidth(160)
        self.publish_loading.setVisible(False)

        # 步骤标签
        step1_label = QLabel("\U0001f4e6 选择素材")
        step1_label.setStyleSheet("font-weight: 700; color: #2563eb; font-size: 13px;")
        step2_label = QLabel("\U0001f464 选择平台和账号")
        step2_label.setStyleSheet("font-weight: 700; color: #2563eb; font-size: 13px;")

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow("标题", self.title)
        form.addRow("话题", topic_widget)

        actions = QHBoxLayout()
        self.publish_button = make_button("发布选中任务", self.publish, primary=True)
        self.refresh_button = make_button("刷新", self.refresh)
        actions.addWidget(self.publish_button)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.publish_loading)
        actions.addWidget(self.publish_status)
        actions.addStretch()

        material_panel = QWidget()
        material_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        material_layout = QVBoxLayout(material_panel)
        material_layout.setContentsMargins(0, 0, 0, 0)
        material_layout.setSpacing(6)
        material_layout.addWidget(step1_label)
        material_layout.addWidget(self.materials)

        account_panel = QWidget()
        account_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        account_layout = QVBoxLayout(account_panel)
        account_layout.setContentsMargins(0, 0, 0, 0)
        account_layout.setSpacing(6)
        account_layout.addWidget(step2_label)
        account_layout.addWidget(self.platform_filter)
        account_layout.addWidget(self.accounts)

        selection_panel = QWidget()
        selection_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        selection_layout = QHBoxLayout(selection_panel)
        selection_layout.setContentsMargins(0, 0, 0, 0)
        selection_layout.setSpacing(10)
        selection_layout.addWidget(material_panel, 1, Qt.AlignTop)
        selection_layout.addWidget(account_panel, 1, Qt.AlignTop)

        publish_form = QWidget()
        publish_form.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        publish_form.setLayout(form)

        actions_widget = QWidget()
        actions_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        actions_widget.setLayout(actions)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(8)
        header = page_header("发布中心", "选择素材和账号后提交发布任务")
        header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header.setMaximumHeight(54)
        layout.addWidget(header)
        layout.addWidget(selection_panel)
        layout.addWidget(publish_form)
        layout.addWidget(actions_widget)
        layout.addWidget(self.log_section)
        layout.addStretch(1)

        self.event_bus.accounts_changed.connect(self.refresh)
        self.event_bus.materials_changed.connect(self.refresh)
        self.event_bus.settings_changed.connect(self._reload_topic_presets)
        self.materials.selection_changed.connect(lambda _: self._auto_fill_title_from_selection())
        self._load_last_selection()
        self._reload_topic_presets()

    def selected_material(self) -> dict | None:
        row = self.materials.currentRow()
        if row < 0:
            return None
        payload = self.materials.get_payload(row)
        return payload if isinstance(payload, dict) else None

    def show_material_context_menu(self, position):
        row = self.materials.rowAt(position.y())
        if row >= 0:
            self.materials.selectRow(row)
        material = self.selected_material()
        if not material:
            return
        menu = QMenu(self)
        preview_action = menu.addAction("打开预览")
        reveal_action = menu.addAction("打开所在文件夹")
        delete_action = menu.addAction("删除")
        action = menu.exec(self.materials.viewport().mapToGlobal(position))
        if action == preview_action:
            self.open_preview()
        elif action == reveal_action:
            self.open_selected_material_location()
        elif action == delete_action:
            self.delete_material()

    def selected_material_path(self):
        material = self.selected_material()
        if not material:
            return None
        relative_path = material.get("file_path") or material.get("filePath")
        if not relative_path:
            return None
        return self.material_service.resolve_material_path(relative_path)

    def open_preview(self):
        path = self.selected_material_path()
        if not path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_selected_material_location(self):
        path = self.selected_material_path()
        if not path:
            return
        if not reveal_file_in_folder(path):
            QMessageBox.warning(self, "打开文件夹", "文件不存在，无法定位。")

    def delete_material(self):
        material = self.selected_material()
        if not material or not material.get("id"):
            return
        if QMessageBox.question(self, "确认删除", "删除选中素材文件和记录？") == QMessageBox.Yes:
            self.material_service.delete_material(material["id"])
            self.event_bus.materials_changed.emit()

    def refresh(self):
        materials = self.material_service.list_materials()
        self._all_accounts = self.account_service.list_accounts()
        self.materials.set_rows(
            [[m.get("filename"), m.get("source_type") or "本地"] for m in materials],
            payloads=materials,
        )
        self._refresh_platform_filter()
        self._apply_account_rows()
        self._auto_fill_title_from_selection()

    def _refresh_platform_filter(self):
        current_value = self.platform_filter.currentData()
        if current_value is None and self._remembered_platform_type is not None:
            current_value = self._remembered_platform_type
        platforms = []
        seen = set()
        for account in self._all_accounts:
            platform_type = account.get("type")
            if platform_type in seen:
                continue
            seen.add(platform_type)
            platforms.append((platform_type, account.get("platform") or str(platform_type)))
        blocker = QSignalBlocker(self.platform_filter)
        self.platform_filter.clear()
        self.platform_filter.addItem("全部平台", None)
        for platform_type, platform_name in platforms:
            self.platform_filter.addItem(platform_name, platform_type)
        target_index = 0
        for index in range(self.platform_filter.count()):
            if self.platform_filter.itemData(index) == current_value:
                target_index = index
                break
        self.platform_filter.setCurrentIndex(target_index)
        del blocker

    def _apply_account_rows(self):
        platform_type = self.platform_filter.currentData()
        accounts = [
            account for account in self._all_accounts
            if platform_type is None or account.get("type") == platform_type
        ]
        self.accounts.set_rows(
            [
                [
                    a.get("platform"),
                    a.get("userName"),
                    "正常" if a.get("status") else "未验证",
                    self._account_publish_results.get(self._account_key(a), "未发布"),
                ]
                for a in accounts
            ],
            payloads=accounts,
        )
        for row in range(self.accounts.rowCount()):
            account = self.accounts.get_payload(row)
            if account and self._account_selection_key(account) in self._remembered_account_keys:
                item = self.accounts.item(row, 0)
                if item:
                    item.setCheckState(Qt.Checked)

    def _on_platform_filter_changed(self):
        self._remember_checked_accounts()
        self._apply_account_rows()

    def publish(self):
        if self._is_publishing:
            return
        jobs = self._selected_publish_jobs()
        if not jobs:
            return
        self._set_publishing_state(True, f"正在发布：{len(jobs)} 个平台")
        self.log_section.set_expanded(True)
        self.log.clear()
        self.log.append(f"开始发布：{len(jobs)} 个平台")
        for job in jobs:
            self._mark_job_accounts(job, "发布中...")
            self.log.append(f"提交发布：{job['platformName']} / {len(job['accounts'])} 个账号")
        self._save_last_selection(jobs)
        run_background(
            self,
            lambda: self._publish_jobs(jobs),
            self._on_publish_done,
            self._on_publish_error,
        )

    def _set_publishing_state(self, active: bool, message: str = ""):
        self._is_publishing = active
        self.publish_button.setEnabled(not active)
        self.refresh_button.setEnabled(not active)
        self.publish_button.setText("发布中..." if active else "发布选中任务")
        self.publish_loading.setVisible(active)
        self.publish_status.setText(message)

    def _publish_jobs(self, jobs: list[dict]) -> list[dict]:
        results = []
        for job in jobs:
            try:
                self.publish_service.publish(job["payload"])
                results.append({**job, "ok": True, "message": "发布成功"})
            except Exception as exc:
                results.append({**job, "ok": False, "message": str(exc)})
        return results

    def _on_publish_done(self, results: list[dict]):
        results = results or []
        success_count = sum(1 for result in results if result.get("ok"))
        fail_count = len(results) - success_count
        for result in results:
            text = "发布成功" if result.get("ok") else f"发布失败：{result.get('message')}"
            self._mark_job_accounts(result, text)
            self.log.append(f"{result['platformName']}：{text}")
        if fail_count:
            self._set_publishing_state(False, f"发布完成：成功 {success_count}，失败 {fail_count}")
            QMessageBox.warning(self, "发布完成", f"发布完成：成功 {success_count} 个平台，失败 {fail_count} 个平台")
        else:
            self._set_publishing_state(False, f"发布成功：{success_count} 个平台")
            QMessageBox.information(self, "发布成功", f"已成功发布 {success_count} 个平台")

    def _on_publish_error(self, error: str):
        self._set_publishing_state(False, "发布失败")
        self.log_section.set_expanded(True)
        self.log.append(f"发布失败：{error}")
        QMessageBox.warning(self, "发布失败", error)

    def add_topic_preset(self):
        self._apply_topic_preset()

    def _apply_topic_preset(self):
        preset_topics = self.topic_preset.currentData() or []
        if not preset_topics:
            return
        self.tags.setText(", ".join(preset_topics))

    def _reload_topic_presets(self):
        current_name = self.topic_preset.currentText()
        presets = self.publish_service.get_topic_presets()
        blocker = QSignalBlocker(self.topic_preset)
        self.topic_preset.clear()
        self.topic_preset.addItem("选择话题预设", [])
        for name, topics in presets.items():
            self.topic_preset.addItem(name, topics)
        target_index = self.topic_preset.findText(current_name)
        self.topic_preset.setCurrentIndex(target_index if target_index >= 0 else 0)
        del blocker

    def _auto_fill_title_from_selection(self):
        if self.title.text().strip() and not self._title_auto_generated:
            return
        title = self._generated_title_from_selected_materials()
        if not title:
            return
        blocker = QSignalBlocker(self.title)
        self.title.setText(title)
        del blocker
        self._title_auto_generated = True

    def _generated_title_from_selected_materials(self) -> str:
        selected_materials = [
            self.materials.get_payload(row)
            for row in self.materials.checked_rows()
        ]
        selected_materials = [item for item in selected_materials if item]
        if not selected_materials:
            return ""
        titles = []
        for material in selected_materials:
            title = (
                material.get("video_title_zh")
                or material.get("videoTitleZh")
                or material.get("video_title")
                or material.get("videoTitle")
                or material.get("filename")
                or ""
            )
            title = str(title).strip()
            if title and title not in titles:
                titles.append(title)
        if not titles:
            return ""
        if len(titles) == 1:
            return self._strip_extension(titles[0])
        return f"{self._strip_extension(titles[0])} 等 {len(titles)} 个素材"

    def _on_title_edited(self):
        self._title_auto_generated = False

    def _selected_publish_payloads(self) -> list[dict]:
        return [job["payload"] for job in self._selected_publish_jobs()]

    def _selected_publish_jobs(self) -> list[dict]:
        material_rows = self.materials.checked_rows()
        account_rows = self.accounts.checked_rows()
        if not material_rows or not account_rows:
            QMessageBox.warning(self, "发布", "请先选择素材和账号")
            return []
        # P0: 使用 payload 而非表格文本获取数据（避免截断问题）
        materials = [self.materials.get_payload(row) for row in material_rows]
        accounts = [self.accounts.get_payload(row) for row in account_rows]
        file_list = [item.get("file_path") for item in materials if item and item.get("file_path")]
        if not file_list:
            QMessageBox.warning(self, "发布", "选中的素材缺少文件路径")
            return []
        accounts_by_platform: dict[int, dict] = {}
        for account in accounts:
            if not account or not account.get("filePath") or not account.get("type"):
                continue
            platform_type = int(account["type"])
            bucket = accounts_by_platform.setdefault(
                platform_type,
                {
                    "platformName": account.get("platform") or str(platform_type),
                    "accounts": [],
                    "accountList": [],
                },
            )
            bucket["accounts"].append(account)
            bucket["accountList"].append(account["filePath"])
        if not accounts_by_platform:
            QMessageBox.warning(self, "发布", "选中的账号缺少平台信息")
            return []
        return [
            {
                "platformType": platform_type,
                "platformName": bucket["platformName"],
                "accounts": bucket["accounts"],
                "payload": {
                    "type": platform_type,
                    "fileList": file_list,
                    "accountList": bucket["accountList"],
                    "title": self.title.text().strip(),
                    "tags": self._parse_tags(),
                },
            }
        for platform_type, bucket in accounts_by_platform.items()
        ]

    def _parse_tags(self) -> list[str]:
        return [tag.strip().lstrip("#") for tag in self.tags.text().split(",") if tag.strip()]

    def _mark_job_accounts(self, job: dict, result_text: str):
        for account in job.get("accounts", []):
            key = self._account_key(account)
            self._account_publish_results[key] = result_text
            for row in range(self.accounts.rowCount()):
                payload = self.accounts.get_payload(row)
                if payload and self._account_key(payload) == key:
                    item = self.accounts.item(row, 4)
                    if item:
                        item.setText(result_text)
                        item.setToolTip(result_text)

    def _account_key(self, account: dict) -> tuple:
        return (
            account.get("id"),
            account.get("type"),
            account.get("filePath"),
            account.get("userName"),
        )

    def _account_selection_key(self, account: dict) -> str:
        return str(account.get("id") or f"{account.get('type')}:{account.get('filePath')}:{account.get('userName')}")

    def _remember_checked_accounts(self):
        for row in self.accounts.checked_rows():
            account = self.accounts.get_payload(row)
            if account:
                self._remembered_account_keys.add(self._account_selection_key(account))

    def _load_last_selection(self):
        selection = self.publish_service.get_last_selection()
        self._remembered_platform_type = selection.get("platformType")
        self._remembered_account_keys = set(selection.get("accountKeys") or [])

    def _save_last_selection(self, jobs: list[dict]):
        account_keys = [
            self._account_selection_key(account)
            for job in jobs
            for account in job.get("accounts", [])
        ]
        platform_type = self.platform_filter.currentData()
        if platform_type is None and len({job.get("platformType") for job in jobs}) == 1:
            platform_type = jobs[0].get("platformType")
        self._remembered_platform_type = platform_type
        self._remembered_account_keys = set(account_keys)
        self.publish_service.save_last_selection({
            "platformType": platform_type,
            "accountKeys": account_keys,
        })

    def _strip_extension(self, title: str) -> str:
        if "." not in title:
            return title
        stem, suffix = title.rsplit(".", 1)
        if suffix.lower() in {"mp4", "mov", "mkv", "avi", "webm", "m4v"}:
            return stem
        return title
