"""关键词编辑对话框 — 表格维护「关键词 + 词汇类别」"""
from pathlib import Path
from typing import Dict, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
)


class KeywordsEditor(QDialog):
    """关键词编辑对话框 — 每行一个关键词，可填写词汇类别"""

    def __init__(self, keywords: List[str],
                 categories: Dict[str, str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑关键词")
        self.resize(560, 480)
        categories = categories or {}
        # 行数据：[(关键词, 类别)]，按传入顺序
        self._rows = [(kw, categories.get(kw, "")) for kw in keywords]

        layout = QVBoxLayout(self)

        # 提示
        hint = QLabel(
            "每行一个关键词，支持中英文混合"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 13px; margin-bottom: 8px; color: palette(window-text); opacity: 0.7;")
        layout.addWidget(hint)

        # 表格
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["词汇类别", "关键词"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.verticalHeader().setVisible(True)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self._update_count)
        layout.addWidget(self.table)

        # 按钮行
        btn_layout = QHBoxLayout()

        btn_add = QPushButton("添加行")
        btn_add.clicked.connect(self._add_row)
        btn_layout.addWidget(btn_add)

        btn_del = QPushButton("删除选中行")
        btn_del.clicked.connect(self._delete_selected)
        btn_layout.addWidget(btn_del)

        btn_import_txt = QPushButton("从 .txt 导入")
        btn_import_txt.clicked.connect(self._import_txt)
        btn_layout.addWidget(btn_import_txt)

        btn_layout.addStretch()

        count_label = QLabel(f"当前: {len(self._rows)} 条")
        count_label.setStyleSheet("font-size: 13px; color: palette(window-text);")
        self._count_label = count_label
        btn_layout.addWidget(count_label)

        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self._clear)
        btn_layout.addWidget(btn_clear)

        btn_ok = QPushButton("保存")
        btn_ok.setDefault(True)
        btn_ok.setStyleSheet("background-color: #4472C4; color: white; padding: 6px 20px; font-size: 14px; border-radius: 4px;")
        btn_ok.clicked.connect(self._save)
        btn_layout.addWidget(btn_ok)

        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

        self._refresh_table()

    # ---------- 表格维护 ----------

    def _make_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        return item

    def _refresh_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._rows))
        for i, (kw, cat) in enumerate(self._rows):
            self.table.setItem(i, 0, self._make_item(cat))
            self.table.setItem(i, 1, self._make_item(kw))
        self.table.blockSignals(False)
        self._update_count()

    def _add_row(self):
        self._collect_from_table()
        self._rows.append(("", ""))
        self._refresh_table()
        self.table.editItem(self.table.item(self.table.rowCount() - 1, 1))

    def _delete_selected(self):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "提示", "请先选中要删除的行")
            return
        self._collect_from_table()
        for r in rows:
            if 0 <= r < len(self._rows):
                del self._rows[r]
        self._refresh_table()

    def _clear(self):
        self._rows = []
        self._refresh_table()

    def _collect_from_table(self):
        """从表格收集当前编辑内容"""
        self._rows = []
        for i in range(self.table.rowCount()):
            cat_item = self.table.item(i, 0)
            kw_item = self.table.item(i, 1)
            kw = kw_item.text().strip() if kw_item else ""
            cat = cat_item.text().strip() if cat_item else ""
            self._rows.append((kw, cat))

    def _update_count(self, *_):
        self._collect_from_table()
        unique = {kw for kw, _ in self._rows if kw}
        self._count_label.setText(f"当前: {len(unique)} 条")

    # ---------- 导入 ----------

    def _import_txt(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择关键词文件", "", "文本文件 (*.txt);;所有文件 (*)")
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"读取文件失败: {e}")
            return
        self._collect_from_table()
        added = 0
        existing = {kw for kw, _ in self._rows if kw}
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            # 支持「词<Tab/逗号/顿号>类别」的可选格式，纯词行类别留空
            kw, cat = line, ""
            for sep in ("\t", "，", ",", "、"):
                if sep in line:
                    left, right = line.split(sep, 1)
                    kw, cat = left.strip(), right.strip()
                    break
            if kw and kw not in existing:
                existing.add(kw)
                self._rows.append((kw, cat))
                added += 1
        self._refresh_table()
        if added == 0:
            QMessageBox.information(self, "导入结果", "没有新关键词（可能全部重复）")

    # ---------- 保存 ----------

    def _save(self):
        self._collect_from_table()
        seen = set()
        keywords: List[str] = []
        categories: Dict[str, str] = {}
        for kw, cat in self._rows:
            if not kw or kw in seen:
                continue
            seen.add(kw)
            keywords.append(kw)
            if cat:
                categories[kw] = cat
        self._keywords = keywords
        self._categories = categories
        self.accept()

    def get_keywords(self) -> List[str]:
        return getattr(self, "_keywords", [kw for kw, _ in self._rows if kw])

    def get_categories(self) -> Dict[str, str]:
        return getattr(self, "_categories", {})
