"""同义词库管理对话框"""
from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QLabel, QLineEdit, QFormLayout,
    QGroupBox, QHeaderView, QMessageBox,
)

from src.config.synonyms_store import SynonymsStore


class SynonymsDialog(QDialog):
    """同义词库管理 — 主词 → 同义词列表"""

    def __init__(self, store: SynonymsStore, keywords=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("同义词库")
        self.resize(700, 500)
        self.store = store
        self._keywords = list(keywords) if keywords else []
        self._data: Dict[str, list] = {}

        self._load()
        self._build_ui()
        self._refresh_table()

    def _load(self):
        self._data = self.store.load()
        # 为关键词列表里没在同义词库里的主词补上空条目
        for kw in self._keywords:
            if kw not in self._data:
                self._data[kw] = []

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        info = QLabel(
            "每行一个主词，同义词列用逗号分隔。"
            "匹配时主词和同义词任一命中都算该主词命中。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 13px; margin-bottom: 4px; color: palette(window-text); opacity: 0.7;")
        layout.addWidget(info)

        # ====== 添加表单 ======
        add_group = QGroupBox("添加/修改同义词")
        add_form = QFormLayout(add_group)
        add_form.setSpacing(6)

        self.input_keyword = QLineEdit()
        self.input_keyword.setPlaceholderText("主词（必须和关键词列表里的一致）")
        add_form.addRow("主词:", self.input_keyword)

        self.input_synonyms = QLineEdit()
        self.input_synonyms.setPlaceholderText("同义词，用逗号分隔，如: 协议,合约,agreement")
        add_form.addRow("同义词:", self.input_synonyms)

        add_btn_row = QHBoxLayout()
        self.btn_add = QPushButton("添加/更新")
        self.btn_add.setDefault(True)
        self.btn_add.clicked.connect(self._add_one)
        add_btn_row.addStretch()
        add_btn_row.addWidget(self.btn_add)
        add_form.addRow("", add_btn_row)

        layout.addWidget(add_group)

        # ====== 表格 ======
        table_group = QGroupBox("已配置同义词（双击可编辑）")
        table_layout = QVBoxLayout(table_group)
        table_layout.setContentsMargins(8, 8, 8, 8)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["主词", "同义词"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        vh = self.table.verticalHeader()
        vh.setVisible(True)
        vh.setDefaultSectionSize(28)
        vh.setSectionResizeMode(QHeaderView.Fixed)
        self.table.setAlternatingRowColors(True)
        self.table.cellChanged.connect(lambda *_: self._save())
        table_layout.addWidget(self.table)

        layout.addWidget(table_group, stretch=1)

        # ====== 按钮行 ======
        btn_layout = QHBoxLayout()

        btn_del = QPushButton("删除选中行")
        btn_del.clicked.connect(self._delete_selected)
        btn_layout.addWidget(btn_del)

        btn_layout.addStretch()

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _refresh_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._data))
        for i, (kw, words) in enumerate(sorted(self._data.items())):
            kw_item = QTableWidgetItem(kw)
            kw_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # 主词列不可编辑
            syn_item = QTableWidgetItem(", ".join(words))
            self.table.setItem(i, 0, kw_item)
            self.table.setItem(i, 1, syn_item)
        self.table.blockSignals(False)

    def _add_one(self):
        kw = self.input_keyword.text().strip()
        syn_text = self.input_synonyms.text().strip()
        if not kw:
            QMessageBox.warning(self, "信息不完整", "请填写主词")
            self.input_keyword.setFocus()
            return
        words = [w.strip() for w in syn_text.split(",") if w.strip()]
        words = [w for w in words if w != kw]  # 主词自身不进同义词列表
        self._data[kw] = words
        self._refresh_table()
        self._save()

        self.input_keyword.clear()
        self.input_synonyms.clear()
        self.input_keyword.setFocus()

    def _delete_selected(self):
        rows = set(idx.row() for idx in self.table.selectedIndexes())
        if not rows:
            QMessageBox.information(self, "提示", "请先选中要删除的行")
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除 {len(rows)} 条同义词记录？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        # 从表格收集当前数据
        self._collect_from_table()
        keys = list(self._data.keys())
        for r in sorted(rows, reverse=True):
            if r < len(keys):
                del self._data[keys[r]]
        self._refresh_table()
        self._save()

    def _collect_from_table(self):
        """从表格收集编辑后的数据"""
        result = {}
        for i in range(self.table.rowCount()):
            kw_item = self.table.item(i, 0)
            syn_item = self.table.item(i, 1)
            kw = kw_item.text().strip() if kw_item else ""
            syn_text = syn_item.text().strip() if syn_item else ""
            if not kw:
                continue
            words = [w.strip() for w in syn_text.split(",") if w.strip()]
            words = [w for w in words if w != kw]
            result[kw] = words
        self._data = result

    def _save(self):
        self._collect_from_table()
        self.store.save(self._data)

    def get_synonyms(self) -> Dict[str, list]:
        self._collect_from_table()
        return self._data
