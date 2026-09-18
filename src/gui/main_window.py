"""主窗口 — 邮件审计工具 GUI"""
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QLabel, QPushButton, QComboBox, QSpinBox, QCheckBox,
    QRadioButton, QButtonGroup, QDateEdit, QLineEdit, QPlainTextEdit,
    QProgressBar, QTableView, QHeaderView, QFileDialog, QMessageBox,
    QTabWidget, QDialog,
)

from src.config.accounts_store import AccountsStore
from src.config.config_manager import Config, ConfigManager
from src.config.crypto import CryptoError
from src.config.synonyms_store import SynonymsStore
from src.core.excel_exporter import ExcelExporter
from src.gui.accounts_dialog import AccountsDialog
from src.gui.keywords_editor import KeywordsEditor
from src.gui.result_model import ResultModel
from src.gui.synonyms_dialog import SynonymsDialog
from src.models.account import Account
from src.models.records import AuditResult
from src.workers.audit_worker import AuditWorker
from src.workers.local_audit_worker import LocalAuditWorker


def _output_root() -> Path:
    """返回 output 目录根路径
    - 源码跑: 项目根/output
    - PyInstaller 打包: exe 所在目录/output (__file__ 指向临时 _MEIPASS，不能用)
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "output"
    return Path(__file__).resolve().parent.parent.parent / "output"

# IMAP 原始文件夹名 → 中文显示名 的默认映射（作为 fallback）
# 服务器返回的 UTF-7 解码后优先使用；这里覆盖预设系统文件夹
_FOLDER_NAME_MAP: dict = {
    # QQ 邮箱（英文 IMAP 名）
    "INBOX": "收件箱",
    "Sent Messages": "已发送",
    "Drafts": "草稿",
    "Deleted Messages": "已删除",
    "Junk": "垃圾邮件",
    # 腾讯企业邮箱（中文 IMAP 名）
    "已发送": "已发送",
    "草稿箱": "草稿箱",
    "已删除": "已删除",
    "垃圾邮件": "垃圾邮件",
    # UTF-7 编码常见值（作为 fallback，正常情况下应已解码）
    "&UXZO1mWHTvZZOQ-": "其他文件夹",
    "&UXZO1mWHTvZZOQ-/QQ&kK5O9ouilgU-": "邮件订阅",
}


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("邮箱关键词审计系统")
        self.resize(1100, 720)

        # Qt 会自动预创建 menu bar / status bar，QSS height:0 压不住，
        # 必须代码里显式 hide，否则底部/顶部会留黑条
        self.menuBar().hide()
        self.statusBar().hide()

        self.config_mgr = ConfigManager()
        self.config: Config = self.config_mgr.load()
        self.accounts_store = AccountsStore()
        self.synonyms_store = SynonymsStore()
        self.accounts: List[Account] = []
        self.worker: Optional[AuditWorker] = None
        self.result: Optional[AuditResult] = None
        self.local_export_dir: Optional[Path] = None  # 本地审计的导出目录（时间戳目录）

        self._initializing = True
        self._build_ui()
        self._apply_config_to_ui()
        self._initializing = False

        try:
            self.accounts = self.accounts_store.load()
        except CryptoError:
            try:
                self.accounts_store.file_path.unlink(missing_ok=True)
            except Exception:
                pass
            self.accounts = []
        self._update_account_label()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16, 16, 16, 16)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, stretch=1)

        # ============ Tab 1: 审计配置 ============
        config_tab = QWidget()
        config_layout = QVBoxLayout(config_tab)
        config_layout.setSpacing(14)

        # --- 审计方式 ---
        mode_group = QGroupBox("审计方式")
        mode_row = QHBoxLayout()
        mode_row.setSpacing(20)
        self.radio_online = QRadioButton("在线审计（连接服务器拉取）")
        self.radio_local = QRadioButton("本地审计（使用已拉取的邮件目录）")
        self.radio_online.setChecked(True)
        self._mode_btn_group = QButtonGroup(self)
        self._mode_btn_group.addButton(self.radio_online)
        self._mode_btn_group.addButton(self.radio_local)
        mode_row.addWidget(self.radio_online)
        mode_row.addWidget(self.radio_local)
        mode_row.addStretch()
        mode_group.setLayout(mode_row)
        config_layout.addWidget(mode_group)

        # --- 本地邮件目录（本地审计时显示） ---
        local_group = QGroupBox("本地邮件目录")
        local_form = QFormLayout(local_group)
        local_form.setLabelAlignment(Qt.AlignRight)
        local_form.setSpacing(10)
        dir_row = QHBoxLayout()
        self.input_local_dir = QLineEdit()
        self.input_local_dir.setReadOnly(True)
        self.input_local_dir.setPlaceholderText("请选择本地邮件目录")
        btn_browse_dir = QPushButton("浏览...")
        btn_browse_dir.clicked.connect(self._browse_local_dir)
        dir_row.addWidget(self.input_local_dir, stretch=1)
        dir_row.addWidget(btn_browse_dir)
        local_form.addRow("邮件根目录:", dir_row)
        lbl_local_hint = QLabel("目录结构: 账号/文件夹/UID.eml；  "
                                "邮件根目录请选择 全部邮件 目录；  "
                                "导出结果将保存到该时间戳目录内（与 全部邮件 同级）")
        lbl_local_hint.setWordWrap(True)
        local_form.addRow("", lbl_local_hint)
        self.local_group = local_group
        local_group.setVisible(False)
        config_layout.addWidget(local_group)

        # --- 服务器 ---
        self.server_group = QGroupBox("服务器")
        self._server_form = QFormLayout(self.server_group)
        self._server_form.setLabelAlignment(Qt.AlignRight)
        self._server_form.setSpacing(10)

        self._mail_presets = {
            "QQ邮箱": {
                "host": "imap.qq.com", "port": 993, "ssl": True,
                "folders": [
                    "INBOX", "Sent Messages", "Drafts", "Deleted Messages",
                    "&UXZO1mWHTvZZOQ-",
                    "&UXZO1mWHTvZZOQ-/QQ&kK5O9ouilgU-",
                ],
                "folder_labels": {
                    "INBOX": "收件箱", "Sent Messages": "已发送",
                    "Drafts": "草稿", "Deleted Messages": "已删除",
                    "&UXZO1mWHTvZZOQ-": "其他文件夹",
                    "&UXZO1mWHTvZZOQ-/QQ&kK5O9ouilgU-": "邮件订阅",
                },
                "junk": "Junk",
            },
            "腾讯企业邮箱": {
                "host": "imap.exmail.qq.com", "port": 993, "ssl": True,
                "folders": [
                    "INBOX", "已发送", "草稿箱", "已删除",
                    "&UXZO1mWHTvZZOQ-",
                    "&UXZO1mWHTvZZOQ-/QQ&kK5O9ouilgU-",
                ],
                "folder_labels": {
                    "INBOX": "收件箱", "已发送": "已发送",
                    "草稿箱": "草稿箱", "已删除": "已删除",
                    "&UXZO1mWHTvZZOQ-": "其他文件夹",
                    "&UXZO1mWHTvZZOQ-/QQ&kK5O9ouilgU-": "邮件订阅",
                },
                "junk": "垃圾邮件",
            },
        }

        self.combo_mail_type = QComboBox()
        self.combo_mail_type.addItems(["腾讯企业邮箱", "QQ邮箱", "自定义"])
        self.combo_mail_type.currentTextChanged.connect(self._on_mail_type_changed)
        self._server_form.addRow("邮箱类型", self.combo_mail_type)

        self.input_host = QLineEdit()
        self.input_port = QSpinBox()
        self.input_port.setRange(1, 65535)
        self.chk_ssl = QCheckBox("SSL")

        # 自定义时手动编辑也要触发保存
        self.input_host.editingFinished.connect(self._save_config)
        self.input_port.valueChanged.connect(self._save_config)
        self.chk_ssl.stateChanged.connect(self._save_config)

        host_row = QHBoxLayout()
        host_row.addWidget(QLabel("主机:"))
        host_row.addWidget(self.input_host, stretch=2)
        host_row.addWidget(QLabel("端口:"))
        host_row.addWidget(self.input_port)
        host_row.addWidget(self.chk_ssl)
        self._server_form.addRow("", host_row)

        # 文件夹
        self.chk_folders = {}
        self.chk_junk = None
        self._folder_row_index = -1
        self._build_folder_checkboxes("腾讯企业邮箱")

        btn_list_folders = QPushButton("测试连接并列出文件夹")
        btn_list_folders.clicked.connect(self._list_server_folders)
        self._server_form.addRow("", btn_list_folders)

        self._apply_preset("腾讯企业邮箱")
        config_layout.addWidget(self.server_group)

        # 审计方式切换（在所有分组创建完成后连接）
        self.radio_online.toggled.connect(self._on_audit_mode_changed)
        self.radio_local.toggled.connect(self._on_audit_mode_changed)

        # --- 审计参数 ---
        param_group = QGroupBox("审计参数")
        param_form = QFormLayout(param_group)
        param_form.setLabelAlignment(Qt.AlignRight)
        param_form.setSpacing(10)

        time_row = QHBoxLayout()
        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        self.date_start.installEventFilter(self)
        self.date_end.installEventFilter(self)
        time_row.addWidget(QLabel("从"))
        time_row.addWidget(self.date_start)
        time_row.addWidget(QLabel("到"))
        time_row.addWidget(self.date_end)
        time_row.addStretch()
        param_form.addRow("时间范围:", time_row)

        kw_row = QHBoxLayout()
        self.lbl_kw_count = QLabel("0 条")
        self.lbl_kw_count.setStyleSheet("font-weight: bold;")
        kw_row.addWidget(self.lbl_kw_count)
        btn_edit_kw = QPushButton("编辑关键词")
        btn_edit_kw.clicked.connect(self._edit_keywords)
        kw_row.addWidget(btn_edit_kw)
        btn_synonyms = QPushButton("同义词库")
        btn_synonyms.clicked.connect(self._manage_synonyms)
        kw_row.addWidget(btn_synonyms)
        kw_row.addStretch()
        param_form.addRow("关键词:", kw_row)

        match_row = QHBoxLayout()
        self.chk_case = QCheckBox("区分大小写")
        match_row.addWidget(self.chk_case)
        match_row.addStretch()
        param_form.addRow("匹配选项:", match_row)

        worker_row = QHBoxLayout()
        self.spin_workers = QSpinBox()
        self.spin_workers.setRange(1, 5)
        self.spin_workers.setValue(2)
        worker_row.addWidget(self.spin_workers)
        worker_row.addWidget(QLabel("个并发（建议 1-3）"))
        worker_row.addStretch()
        param_form.addRow("并发数:", worker_row)

        acc_row = QHBoxLayout()
        self.lbl_acc_count = QLabel("0 个")
        self.lbl_acc_count.setStyleSheet("font-weight: bold;")
        acc_row.addWidget(self.lbl_acc_count)
        btn_manage_acc = QPushButton("账号管理")
        btn_manage_acc.clicked.connect(self._manage_accounts)
        acc_row.addWidget(btn_manage_acc)
        acc_row.addStretch()
        param_form.addRow("邮箱账号:", acc_row)

        config_layout.addWidget(param_group)
        config_layout.addStretch()
        self.tabs.addTab(config_tab, "审计配置")

        # ============ Tab 2: 进度日志 ============
        progress_tab = QWidget()
        prog_layout = QVBoxLayout(progress_tab)

        prog_bar_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        prog_bar_row.addWidget(self.progress_bar, stretch=1)
        self.lbl_progress = QLabel("就绪")
        self.lbl_progress.setMinimumWidth(180)
        prog_bar_row.addWidget(self.lbl_progress)
        prog_layout.addLayout(prog_bar_row)

        prog_layout.addWidget(QLabel("实时日志:"))
        self.log_text = QPlainTextEdit()
        self.log_text.setObjectName("logText")
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(5000)
        prog_layout.addWidget(self.log_text)

        self.tabs.addTab(progress_tab, "进度日志")

        # ============ Tab 3: 命中预览 ============
        result_tab = QWidget()
        result_layout = QVBoxLayout(result_tab)

        result_top = QHBoxLayout()
        self.lbl_result_summary = QLabel("尚未执行审计")
        self.lbl_result_summary.setStyleSheet("font-size: 14px; font-weight: bold;")
        result_top.addWidget(self.lbl_result_summary)
        result_top.addStretch()
        btn_open_eml = QPushButton("打开选中邮件")
        btn_open_eml.clicked.connect(self._open_selected_eml)
        result_top.addWidget(btn_open_eml)
        result_layout.addLayout(result_top)

        self.table_view = QTableView()
        self.result_model = ResultModel()
        self.table_view.setModel(self.result_model)
        self.table_view.setSelectionBehavior(QTableView.SelectRows)
        self.table_view.setSelectionMode(QTableView.SingleSelection)
        self.table_view.setEditTriggers(QTableView.NoEditTriggers)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        # 初始列宽
        header = self.table_view.horizontalHeader()
        header.resizeSection(0, 100)   # 姓名
        header.resizeSection(1, 180)   # 账号
        header.resizeSection(2, 100)   # 文件夹
        header.resizeSection(3, 50)    # UID
        header.resizeSection(4, 130)   # 日期
        header.resizeSection(5, 180)   # 发件人
        header.resizeSection(6, 200)   # 主题
        header.resizeSection(7, 90)    # 词汇类别
        header.resizeSection(8, 120)   # 命中关键词
        header.resizeSection(9, 120)   # 命中同义词
        header.resizeSection(10, 80)   # 命中字段
        header.resizeSection(11, 250)  # 命中内容
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.verticalHeader().setDefaultSectionSize(30)
        self.table_view.doubleClicked.connect(self._on_table_double_click)
        result_layout.addWidget(self.table_view)

        self.tabs.addTab(result_tab, "命中预览")

        # ============ Tab 4: 审计历史 ============
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        history_layout.setContentsMargins(4, 4, 4, 4)
        history_layout.setSpacing(12)

        hist_top = QHBoxLayout()
        btn_refresh_hist = QPushButton("刷新")
        btn_refresh_hist.clicked.connect(self._refresh_history)
        hist_top.addWidget(btn_refresh_hist)
        hist_top.addStretch()
        btn_open_hist_dir = QPushButton("打开该次目录")
        btn_open_hist_dir.clicked.connect(self._open_history_item_dir)
        hist_top.addWidget(btn_open_hist_dir)
        btn_load_hist = QPushButton("加载到命中预览")
        btn_load_hist.clicked.connect(self._load_history_item)
        hist_top.addWidget(btn_load_hist)
        history_layout.addLayout(hist_top)

        self.history_table = QTableView()
        self.history_table.setSelectionBehavior(QTableView.SelectRows)
        self.history_table.setSelectionMode(QTableView.SingleSelection)
        self.history_table.setEditTriggers(QTableView.NoEditTriggers)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.verticalHeader().setDefaultSectionSize(34)
        # 所有列自动拉伸填满宽度
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.doubleClicked.connect(lambda idx: self._load_history_item())
        history_layout.addWidget(self.history_table)

        self.tabs.addTab(history_tab, "审计历史")

        self._refresh_history()

        # ============ 底部操作栏 ============
        bottom = QHBoxLayout()
        bottom.setSpacing(10)

        self.btn_start = QPushButton("开始审计")
        self.btn_start.setObjectName("btnPrimary")
        self.btn_start.clicked.connect(self._start_audit)
        bottom.addWidget(self.btn_start)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_audit)
        bottom.addWidget(self.btn_cancel)

        self.btn_export = QPushButton("导出审计结果")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export_excel)
        bottom.addWidget(self.btn_export)

        self.btn_open_dir = QPushButton("打开输出目录")
        self.btn_open_dir.clicked.connect(self._open_output_dir)
        bottom.addWidget(self.btn_open_dir)

        bottom.addStretch()
        main_layout.addLayout(bottom)

    # ==================== UI 同步 ====================

    def _save_config(self):
        """UI 变化时持久化配置（初始化阶段跳过，避免覆盖上次的值）"""
        if not self._initializing:
            self.config_mgr.save(self._collect_config_from_ui())

    def _apply_config_to_ui(self):
        # 优先用持久化的 server_key 恢复上次使用的邮箱类型；失效时按 host 兜底
        target = self.config.server_key
        if target not in ("腾讯企业邮箱", "QQ邮箱", "自定义"):
            target = "自定义"
            for name, p in self._mail_presets.items():
                if p["host"] == self.config.host:
                    target = name
                    break
        self.combo_mail_type.setCurrentText(target)
        if target == "自定义":
            self.input_host.setText(self.config.host)
            self.input_port.setValue(self.config.port)
            self.chk_ssl.setChecked(self.config.use_ssl)

        # 恢复审计方式与本地目录
        if self.config.audit_mode == "local":
            self.radio_local.setChecked(True)
        else:
            self.radio_online.setChecked(True)
        self.input_local_dir.setText(self.config.local_dir)

        for chk in self.chk_folders.values():
            imap_name = chk.property("imap_name")
            chk.setChecked(imap_name in self.config.scan_folders)
        if self.chk_junk:
            self.chk_junk.setChecked(self.config.include_junk)

        try:
            self.date_start.setDate(date.fromisoformat(self.config.date_start))
            self.date_end.setDate(date.fromisoformat(self.config.date_end))
        except (ValueError, TypeError):
            today = date.today()
            self.date_start.setDate(today.replace(day=1))
            self.date_end.setDate(today)

        self._update_keyword_label()

        self.chk_case.setChecked(self.config.case_sensitive)
        self.spin_workers.setValue(self.config.max_workers)

    def _collect_config_from_ui(self) -> Config:
        self.config.server_key = self.combo_mail_type.currentText()
        self.config.audit_mode = "local" if self.radio_local.isChecked() else "online"
        self.config.local_dir = self.input_local_dir.text().strip()
        self.config.host = self.input_host.text().strip()
        self.config.port = self.input_port.value()
        self.config.use_ssl = self.chk_ssl.isChecked()

        self.config.scan_folders = [
            c.property("imap_name") or k
            for k, c in self.chk_folders.items() if c.isChecked()
        ]
        junk_name = ""
        if self.chk_junk and self.chk_junk.isChecked():
            junk_name = self.chk_junk.property("imap_name") or ""
        self.config.include_junk = bool(junk_name)
        self.config.junk_folder = junk_name

        self.config.date_start = self.date_start.date().toString("yyyy-MM-dd")
        self.config.date_end = self.date_end.date().toString("yyyy-MM-dd")

        self.config.match_mode = "phrase"
        self.config.case_sensitive = self.chk_case.isChecked()
        self.config.max_workers = self.spin_workers.value()

        return self.config

    def _build_folder_display_map(self) -> dict:
        """从 UI checkbox 提取 IMAP 原始名 → 中文显示名的完整映射"""
        mapping = {}
        # 所有当前显示的 checkbox
        for chk in list(self.chk_folders.values()):
            raw = chk.property("imap_name")
            display = chk.property("display_name") or chk.text()
            if raw:
                mapping[raw] = display
        if self.chk_junk:
            raw = self.chk_junk.property("imap_name")
            display = self.chk_junk.property("display_name") or self.chk_junk.text()
            if raw:
                mapping[raw] = display
        # 默认映射中的预设置（作为补充）
        for raw, display in _FOLDER_NAME_MAP.items():
            if raw not in mapping:
                mapping[raw] = display
        return mapping

    # ==================== 审计方式切换 ====================

    def _on_audit_mode_changed(self):
        local_mode = self.radio_local.isChecked()
        self.server_group.setVisible(not local_mode)
        self.local_group.setVisible(local_mode)
        self._save_config()

    def _browse_local_dir(self):
        chosen = QFileDialog.getExistingDirectory(
            self, "选择本地邮件目录", self.input_local_dir.text() or str(_output_root()))
        if not chosen:
            return
        root = Path(chosen)
        # 若选择的是时间戳目录（其下有 全部邮件），自动下钻一层
        if (root / "全部邮件").is_dir():
            root = root / "全部邮件"
        self.input_local_dir.setText(str(root))
        self._save_config()
        self._log(f"本地邮件目录: {root}")

    # ==================== 邮箱类型切换 ====================

    def _apply_preset(self, preset_name: str):
        if preset_name not in self._mail_presets:
            return
        p = self._mail_presets[preset_name]
        self.input_host.setText(p["host"])
        self.input_port.setValue(p["port"])
        self.chk_ssl.setChecked(p["ssl"])
        self._rebuild_folder_checkboxes(preset_name)

    def _on_mail_type_changed(self, text: str):
        if text in self._mail_presets:
            self._apply_preset(text)
            self.input_host.setReadOnly(True)
            self.input_port.setReadOnly(True)
            self.chk_ssl.setEnabled(False)
        elif text == "自定义":
            self.input_host.setReadOnly(False)
            self.input_port.setReadOnly(False)
            self.chk_ssl.setEnabled(True)
            self.input_host.clear()
            self.input_port.setValue(993)
        # 切换后立即保存
        self._save_config()

    def _list_server_folders(self):
        accounts = self.accounts_store.load()
        if not accounts:
            QMessageBox.information(self, "提示", "请先添加邮箱账号")
            return

        cfg = self._collect_config_from_ui()
        acc = accounts[0]

        self._log(f"连接 {cfg.host}:{cfg.port} ...")
        try:
            from src.core.imap_client import ImapClient
            client = ImapClient(host=cfg.host, port=cfg.port, use_ssl=cfg.use_ssl)
            client.connect(acc.email, acc.auth_code)
            folders_info = client.list_folders()  # List[dict], 含 raw/name/flags
            folder_with_count = []
            for f in folders_info:
                raw = f["raw"]
                name = f["name"]
                try:
                    count = client.select_folder(raw)
                except Exception:
                    count = -1
                folder_with_count.append((raw, name, count, f["flags"]))
            client.logout()

            self._log(f"服务器返回 {len(folder_with_count)} 个文件夹:")
            for raw, name, count, flags in folder_with_count:
                display = _FOLDER_NAME_MAP.get(raw, name)
                self._log(f"  {display} ({raw}): {count} 封  [{flags}]")

            # 动态重建文件夹复选框
            self._rebuild_folder_checkboxes_from_server(folder_with_count, cfg)

            # 弹出确认
            lines = [f"{_FOLDER_NAME_MAP.get(raw, name)}  ({count}封)"
                     for raw, name, count, flags in folder_with_count]
            QMessageBox.information(self, "服务器文件夹已同步",
                f"共 {len(folder_with_count)} 个文件夹，已更新到界面。\n\n" + "\n".join(lines))
        except Exception as e:
            self._log(f"连接失败: {e}")
            QMessageBox.warning(self, "连接失败", str(e))

    def _rebuild_folder_checkboxes_from_server(self, folder_with_count, cfg):
        """根据服务器返回的文件夹列表重建复选框区域"""
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)

        row_layout.addWidget(QLabel("扫描文件夹:"))
        row_layout.addStretch()

        # 把服务器文件夹整理成有顺序的列表
        # 预设系统文件夹优先，其他自定义文件夹按字母序追加
        preset_order = ["INBOX", "已发送", "Sent Messages", "草稿箱", "Drafts",
                        "已删除", "Deleted Messages", "垃圾邮件", "Junk"]

        sys_folders = []   # 预设的系统文件夹
        custom_folders = []  # 自定义文件夹

        for raw, name, count, flags in folder_with_count:
            # 先用预设映射翻译一遍（服务器返回的 ASCII 名如 INBOX 解码后还是英文）
            display = _FOLDER_NAME_MAP.get(raw, name)
            if raw.upper() == "INBOX":
                sys_folders.insert(0, (raw, display))
            elif raw in preset_order or display in ["垃圾邮件", "Junk"]:
                sys_folders.append((raw, display))
            else:
                custom_folders.append((raw, display))

        # sys_folders 按 preset_order 排序
        order_key = {p: i for i, p in enumerate(preset_order)}
        sys_folders.sort(key=lambda x: order_key.get(x[0], 999))
        # INBOX 永远在最前
        sys_folders.sort(key=lambda x: 0 if x[0].upper() == "INBOX" else 1)

        # 合并: 系统文件夹 + 自定义文件夹
        all_folders = sys_folders + custom_folders

        self.chk_folders = {}
        self.chk_junk = None

        for raw, name in all_folders:
            # 跳过垃圾邮件（它有独立的复选框）
            if raw in ("垃圾邮件", "Junk") or name in ("垃圾邮件", "Junk"):
                self.chk_junk = QCheckBox(name)
                self.chk_junk.setProperty("imap_name", raw)
                self.chk_junk.setProperty("display_name", name)
                self.chk_junk.setChecked(True)
                continue

            # 检查是否已经在 scan_folders 配置中
            default_checked = (raw in cfg.scan_folders) or (not cfg.scan_folders)  # 没配置过就全选

            chk = QCheckBox(name)
            chk.setProperty("imap_name", raw)
            chk.setProperty("display_name", name)
            chk.setChecked(default_checked)
            self.chk_folders[raw] = chk
            row_layout.addWidget(chk)

        # 垃圾邮件复选框追加
        if self.chk_junk:
            row_layout.addWidget(self.chk_junk)

        # 更新 junk_folder 配置
        if self.chk_junk:
            self.config.junk_folder = self.chk_junk.property("imap_name")

        row_layout.addStretch()

        # 替换旧的行
        if self._folder_row_index >= 0:
            self._server_form.removeRow(self._folder_row_index)
        self._server_form.insertRow(self._folder_row_index, row_widget)
        self._folder_row_widget = row_widget

    def _create_folder_row_widget(self, preset_name: str):
        p = self._mail_presets[preset_name]
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)

        row_layout.addWidget(QLabel("扫描文件夹:"))
        row_layout.addStretch()

        self.chk_folders = {}
        for folder_key in p["folders"]:
            label = p["folder_labels"].get(folder_key, folder_key)
            chk = QCheckBox(label)
            chk.setChecked(True)
            chk.setProperty("imap_name", folder_key)
            chk.setProperty("display_name", label)
            self.chk_folders[folder_key] = chk
            row_layout.addWidget(chk)

        junk_label = p["junk"]
        junk_display = p.get("junk_label", "垃圾邮件")
        self.chk_junk = QCheckBox(junk_display)
        self.chk_junk.setProperty("imap_name", junk_label)
        self.chk_junk.setProperty("display_name", junk_display)
        self.chk_junk.setChecked(True)
        row_layout.addWidget(self.chk_junk)
        row_layout.addStretch()
        return row_widget

    def _build_folder_checkboxes(self, preset_name: str):
        row_widget = self._create_folder_row_widget(preset_name)
        self._server_form.addRow(row_widget)
        self._folder_row_index = self._server_form.rowCount() - 1
        self._folder_row_widget = row_widget

    def _rebuild_folder_checkboxes(self, preset_name: str):
        new_widget = self._create_folder_row_widget(preset_name)
        if self._folder_row_index >= 0:
            self._server_form.removeRow(self._folder_row_index)
        self._server_form.insertRow(self._folder_row_index, new_widget)
        self._folder_row_widget = new_widget

    def _update_keyword_label(self):
        self.lbl_kw_count.setText(f"{len(self.config.keywords)} 条")

    def _update_account_label(self):
        self.lbl_acc_count.setText(f"{len(self.accounts)} 个")

    # ==================== 关键词 / 账号 ====================

    def _edit_keywords(self):
        dlg = KeywordsEditor(self.config.keywords,
                             categories=self.config.keyword_category, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self.config.keywords = dlg.get_keywords()
            self.config.keyword_category = dlg.get_categories()
            self._update_keyword_label()
            self.config_mgr.save(self.config)
            self._log(f"关键词已更新: {len(self.config.keywords)} 条")

    def _merged_categories(self) -> dict:
        """合并关键词编辑器与同义词库中的类别（关键词编辑器优先）"""
        merged = {}
        for kw, info in self.synonyms_store.load_full().items():
            cat = info.get("category", "")
            if cat:
                merged[kw] = cat
        for kw, cat in self.config.keyword_category.items():
            if cat:
                merged[kw] = cat
        return merged

    def _manage_accounts(self):
        dlg = AccountsDialog(self.accounts_store, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self.accounts = dlg.get_accounts()
            self._update_account_label()
            self._log(f"账号已更新: {len(self.accounts)} 个")

    def _manage_synonyms(self):
        dlg = SynonymsDialog(self.synonyms_store,
                             keywords=self.config.keywords,
                             categories=self.config.keyword_category, parent=self)
        dlg.exec()
        syn = self.synonyms_store.load()
        total = sum(len(v) for v in syn.values())
        # 将同义词库里维护的类别同步回配置（仅补充当前关键词中尚无类别的主词）
        full = self.synonyms_store.load_full()
        changed = False
        for kw in self.config.keywords:
            cat = full.get(kw, {}).get("category", "")
            if cat and not self.config.keyword_category.get(kw):
                self.config.keyword_category[kw] = cat
                changed = True
        if changed:
            self.config_mgr.save(self.config)
        self._log(f"同义词库已更新: {len(syn)} 个主词, {total} 个同义词")

    # ==================== 审计 ====================

    def _start_audit(self):
        cfg = self._collect_config_from_ui()
        self.config_mgr.save(cfg)

        d_start = self.date_start.date().toPython()
        d_end = self.date_end.date().toPython()
        local_mode = self.radio_local.isChecked()

        problems = []
        if not self.config.keywords:
            problems.append("未编辑关键词")
        if d_start > d_end:
            problems.append("开始日期晚于结束日期")
        if local_mode:
            src = self.input_local_dir.text().strip()
            if not src or not Path(src).is_dir():
                problems.append("本地邮件目录无效，请重新选择")
        else:
            if not self.accounts:
                problems.append("未配置邮箱账号")
            if not cfg.scan_folders and not cfg.include_junk:
                problems.append("未选择扫描文件夹")

        if problems:
            detail = "\n".join(f"  - {p}" for p in problems)
            QMessageBox.warning(self, "无法开始", f"需先修复:\n{detail}")
            return

        self.tabs.setCurrentIndex(1)
        self.log_text.clear()
        self.progress_bar.setValue(0)

        if local_mode:
            # 解析导出目录：选的是 全部邮件 → 其上层时间戳目录；
            # 选的本身就是时间戳目录 → 直接用；其余情况走 output 下新建时间戳目录
            src_path = Path(self.input_local_dir.text().strip())
            export_dir = None
            if src_path.name == "全部邮件":
                export_dir = src_path.parent
            elif re.match(r'^\d{8}_\d{6,8}$', src_path.name):
                export_dir = src_path
            self.local_export_dir = export_dir

            self.worker = LocalAuditWorker(
                source_dir=src_path,
                accounts=self.accounts,
                keywords=self.config.keywords,
                date_start=d_start,
                date_end=d_end,
                case_sensitive=cfg.case_sensitive,
                match_mode=cfg.match_mode,
                max_workers=cfg.max_workers,
                output_dir=_output_root(),
                synonyms=self.synonyms_store.load(),
                export_dir=export_dir,
                categories=self._merged_categories(),
            )
            self._log(f"本地审计开始 | 目录: {self.input_local_dir.text().strip()} | "
                      f"{len(self.config.keywords)} 关键词 | {d_start} ~ {d_end}")
            if export_dir:
                self._log(f"导出目录: {export_dir}（与 全部邮件 同级）")
        else:
            self.local_export_dir = None
            folder_labels = self._build_folder_display_map()

            self.worker = AuditWorker(
                accounts=self.accounts,
                keywords=self.config.keywords,
                date_start=d_start,
                date_end=d_end,
                host=cfg.host,
                port=cfg.port,
                use_ssl=cfg.use_ssl,
                scan_folders=cfg.scan_folders,
                include_junk=cfg.include_junk,
                junk_folder=cfg.junk_folder,
                folder_labels=folder_labels,
                match_mode=cfg.match_mode,
                case_sensitive=cfg.case_sensitive,
                max_workers=cfg.max_workers,
                output_dir=_output_root(),
                synonyms=self.synonyms_store.load(),
                categories=self._merged_categories(),
            )
            self._log(f"审计开始 | {len(self.accounts)} 账号 | "
                      f"{len(self.config.keywords)} 关键词 | {d_start} ~ {d_end}")
        self.worker.progress.connect(self._on_progress)
        self.worker.account_started.connect(self._on_account_started)
        self.worker.account_done.connect(self._on_account_done)
        self.worker.account_failed.connect(self._on_account_failed)
        self.worker.folder_done.connect(self._on_folder_done)
        self.worker.log.connect(self._log)
        self.worker.finished_ok.connect(self._on_audit_finished)

        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_export.setEnabled(False)

        self.worker.start()

    def _cancel_audit(self):
        if self.worker and self.worker.isRunning():
            if QMessageBox.question(self, "确认", "确定要取消吗？") == QMessageBox.Yes:
                self.worker.cancel()
                self._log("正在取消...")

    def _on_progress(self, current, total, msg):
        if total > 0:
            self.progress_bar.setValue(int(current / total * 100))
        self.lbl_progress.setText(msg)

    def _on_account_started(self, email):
        self.lbl_progress.setText(f"审计中: {email}")

    def _on_account_done(self, email, hit_count):
        self._log(f"[完成] {email} 命中 {hit_count} 封")

    def _on_account_failed(self, email, error):
        self._log(f"[失败] {email}: {error}")

    def _on_folder_done(self, email, folder, hits):
        if hits > 0:
            self._log(f"  {folder}: 命中 {hits} 封")

    def _on_audit_finished(self, result: AuditResult):
        self.result = result
        total = result.total_hits()
        self._log(f"审计完成: 共命中 {total} 封")
        if result.failures:
            for em, err in result.failures.items():
                self._log(f"  [失败] {em}: {err}")

        self.progress_bar.setValue(100)
        self.lbl_progress.setText(f"完成 — 命中 {total} 封")
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_export.setEnabled(total > 0)

        self.result_model.set_result(result)
        self.lbl_result_summary.setText(
            f"命中 {total} 封 | {len(result.account_stats)} 账号 | "
            f"失败 {len(result.failures)}"
        )
        self.tabs.setCurrentIndex(2)

    # ==================== 导出 ====================

    def _export_excel(self):
        if not self.result:
            return
        try:
            if self.local_export_dir and self.local_export_dir.is_dir():
                # 本地审计：导出到所选目录的时间戳文件夹内（与 全部邮件 同级）
                export_path = self.local_export_dir
            else:
                out_base = _output_root()
                out_base.mkdir(parents=True, exist_ok=True)
                ts_dirs = sorted([d for d in out_base.iterdir() if d.is_dir()],
                                 key=lambda d: d.stat().st_mtime, reverse=True)
                export_path = ts_dirs[0] if ts_dirs else out_base

            # 1. 复制命中邮件 .eml → 命中邮件/姓名/文件夹/UID.eml
            eml_out = export_path / "命中邮件"
            eml_out.mkdir(parents=True, exist_ok=True)
            copied = 0
            from src.core.eml_exporter import EmlExporter
            for rec in self.result.records:
                if rec.eml_path:
                    src = Path(rec.eml_path)
                    if src.exists():
                        safe_account = EmlExporter._sanitize(
                            (rec.account_name or rec.account).strip() or rec.account.replace("@", "_at_")
                        )
                        safe_folder = EmlExporter._sanitize(rec.folder)
                        target_dir = eml_out / safe_account / safe_folder
                        target_dir.mkdir(parents=True, exist_ok=True)
                        dst = target_dir / src.name
                        shutil.copy2(src, dst)
                        rec.eml_path = str(dst)
                        copied += 1

            # 2. 导出 Excel（eml_path 已更新为命中邮件路径）
            xlsx_path = export_path / "关键词检索命中记录.xlsx"
            ExcelExporter().export(self.result, str(xlsx_path))

            QMessageBox.information(
                self, "导出成功",
                f"已导出到:\n{export_path}\n\n"
                f"  Excel: {xlsx_path.name}\n"
                f"  命中邮件: {copied} 封 → 命中邮件/"
            )
            self._log(f"导出完成: Excel + {copied} 封命中邮件 → {export_path}")
            if sys.platform == "win32":
                os.startfile(str(export_path))
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _open_output_dir(self):
        out_dir = _output_root()
        out_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(out_dir))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(out_dir)])
        else:
            subprocess.Popen(["xdg-open", str(out_dir)])

    def _open_selected_eml(self):
        idx = self.table_view.currentIndex()
        if not idx.isValid():
            QMessageBox.information(self, "提示", "请先选择一封邮件")
            return
        record = self.result_model.get_record(idx.row())
        if record and record.eml_path:
            path = Path(record.eml_path)
            if path.exists():
                if sys.platform == "win32":
                    os.startfile(str(path))
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(path)])
                else:
                    subprocess.Popen(["xdg-open", str(path)])
            else:
                QMessageBox.warning(self, "文件不存在", str(path))

    def _on_table_double_click(self, idx):
        self._open_selected_eml()

    # ==================== 审计历史 ====================

    def _refresh_history(self):
        import re
        out_base = _output_root()
        if not out_base.exists():
            self.history_table.setModel(self._make_history_model([]))
            return

        ts_pat = re.compile(r'^\d{8}_\d{6,8}$')
        items = []
        for d in sorted(out_base.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not d.is_dir():
                continue
            name = d.name
            if not ts_pat.match(name):
                continue
            # 统计
            all_dir = d / "全部邮件"
            total_eml = 0
            account_names = set()
            if all_dir.exists():
                for acc_dir in all_dir.iterdir():
                    if acc_dir.is_dir():
                        account_names.add(acc_dir.name)
                        for f in acc_dir.rglob("*.eml"):
                            total_eml += 1
            # 命中邮件
            hit_dir = d / "命中邮件"
            hit_eml = 0
            if hit_dir.exists():
                for f in hit_dir.rglob("*.eml"):
                    hit_eml += 1
            # Excel
            has_xlsx = (d / "关键词检索命中记录.xlsx").exists()
            items.append({
                "ts": name,
                "time": name.replace("_", " "),
                "accounts": len(account_names),
                "total": total_eml,
                "hits": hit_eml,
                "xlsx": has_xlsx,
                "path": str(d),
            })

        self._history_items = items
        self.history_table.setModel(self._make_history_model(items))

    def _make_history_model(self, items):
        from PySide6.QtCore import QAbstractTableModel
        HEADERS = ["审计时间", "账号数", "邮件总数", "命中数", "Excel", "目录"]

        class _Model(QAbstractTableModel):
            def __init__(self, items):
                super().__init__()
                self._items = items

            def rowCount(self, parent=None):
                return len(self._items)

            def columnCount(self, parent=None):
                return len(HEADERS)

            def headerData(self, section, orientation, role=Qt.DisplayRole):
                if role == Qt.DisplayRole and orientation == Qt.Horizontal:
                    return HEADERS[section]
                return None

            def data(self, index, role=Qt.DisplayRole):
                if not index.isValid():
                    return None
                it = self._items[index.row()]
                col = index.column()
                if role == Qt.DisplayRole:
                    if col == 0: return it["time"]
                    if col == 1: return str(it["accounts"])
                    if col == 2: return str(it["total"])
                    if col == 3: return str(it["hits"])
                    if col == 4: return "✓" if it["xlsx"] else "—"
                    if col == 5: return it["path"]
                elif role == Qt.ToolTipRole:
                    return it["path"]
                return None

        return _Model(items)

    def _get_selected_history_item(self):
        idx = self.history_table.currentIndex()
        if not idx.isValid() or not hasattr(self, '_history_items'):
            return None
        row = idx.row()
        if 0 <= row < len(self._history_items):
            return self._history_items[row]
        return None

    def _open_history_item_dir(self):
        item = self._get_selected_history_item()
        if not item:
            QMessageBox.information(self, "提示", "请先选择一条历史记录")
            return
        if sys.platform == "win32":
            os.startfile(item["path"])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", item["path"]])
        else:
            subprocess.Popen(["xdg-open", item["path"]])

    def _load_history_item(self):
        item = self._get_selected_history_item()
        if not item:
            QMessageBox.information(self, "提示", "请先选择一条历史记录")
            return

        xlsx_path = Path(item["path"]) / "关键词检索命中记录.xlsx"
        if not xlsx_path.exists():
            QMessageBox.information(self, "提示", "该次审计没有 Excel 导出文件")
            return

        import openpyxl
        from src.models.records import AuditResult, HitRecord

        result = AuditResult()
        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            wb.close()
            return

        headers = [str(c).strip() if c is not None else "" for c in rows[0]]
        idx = {h: i for i, h in enumerate(headers) if h}

        for row in rows[1:]:
            if not row or all(c is None or str(c).strip() == "" for c in row):
                continue
            account = str(row[idx.get("账号", 1)] or "")
            account_name = str(row[idx.get("姓名", 0)] or account)
            hit_kw_raw = str(row[idx.get("命中关键词", 9)] or "")
            hit_synonym_raw = str(row[idx["命中同义词"]] or "") if "命中同义词" in idx else ""
            hit_fields_raw = str(row[idx.get("命中字段", 10)] or "")
            hit_content = str(row[idx.get("命中内容", 11)] or "")
            eml_path = str(row[idx.get("EML路径", 12)] or "")
            hit_keywords = [k.strip() for k in hit_kw_raw.replace("\n", ",").split(",") if k.strip()]
            hit_synonym = [s.strip() for s in hit_synonym_raw.replace("\n", ",").split(",") if s.strip()]
            hit_fields = [f.strip() for f in hit_fields_raw.replace("\n", ",").split(",") if f.strip()]
            # 词汇类别在 Excel 中按行存储、与命中关键词一一对应；旧文件无此列时补空
            hit_cat_raw = str(row[idx["词汇类别"]] or "") if "词汇类别" in idx else ""
            hit_categories = [c.strip() for c in hit_cat_raw.split("\n")]
            if len(hit_categories) < len(hit_keywords):
                hit_categories += [""] * (len(hit_keywords) - len(hit_categories))
            else:
                hit_categories = hit_categories[:len(hit_keywords)]

            hit = HitRecord(
                account=account,
                account_name=account_name,
                folder=str(row[idx.get("文件夹", 2)] or ""),
                uid=int(row[idx.get("UID", 3)] or 0),
                date=str(row[idx.get("日期", 4)] or ""),
                from_=str(row[idx.get("发件人", 5)] or ""),
                to=str(row[idx.get("收件人", 6)] or ""),
                cc=str(row[idx.get("抄送", 7)] or ""),
                subject=str(row[idx.get("主题", 8)] or ""),
                hit_keywords=hit_keywords,
                hit_categories=hit_categories,
                hit_synonym=hit_synonym,
                hit_fields=hit_fields,
                hit_content=hit_content,
                eml_path=eml_path,
            )
            result.add_record(hit)

        wb.close()
        self.result = result
        self.result_model.set_result(result)
        self.lbl_result_summary.setText(
            f"加载历史: 命中 {result.total_hits()} 封 | {item['time']}"
        )
        self.tabs.setCurrentIndex(2)
        self._log(f"已从 Excel 加载历史: {item['time']} — {result.total_hits()} 封命中")

    # ==================== 日志 ====================

    def _log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.appendPlainText(f"[{timestamp}] {msg}")

    # ==================== 关闭 ====================

    def eventFilter(self, obj, event):
        """日历弹窗显示时修复列宽"""
        from PySide6.QtCore import QEvent
        if obj in (self.date_start, self.date_end):
            if event.type() == QEvent.Show:
                cal = obj.calendarWidget()
                if cal:
                    table = cal.findChild(QTableView)
                    if table:
                        table.horizontalHeader().setDefaultSectionSize(36)
                        table.verticalHeader().setDefaultSectionSize(32)
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            if QMessageBox.question(self, "确认退出",
                    "审计任务运行中，确定退出？") != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.cancel()
            self.worker.wait(3000)

        try:
            self.config_mgr.save(self._collect_config_from_ui())
        except Exception:
            pass
        event.accept()
