"""结果表格模型 — QTableView 数据源"""
from typing import List, Optional

from PySide6.QtCore import QAbstractTableModel, Qt

from src.models.records import AuditResult, HitRecord


class ResultModel(QAbstractTableModel):
    """命中记录表格模型"""

    HEADERS = ["姓名", "账号", "文件夹", "UID", "日期", "发件人", "主题", "命中关键词", "命中同义词", "命中字段", "命中内容"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._records: List[HitRecord] = []

    def set_result(self, result: AuditResult):
        self.beginResetModel()
        self._records = list(result.records)
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._records = []
        self.endResetModel()

    def rowCount(self, parent=None):
        return len(self._records)

    def columnCount(self, parent=None):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r = self._records[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            if col == 0: return r.account_name
            if col == 1: return r.account
            if col == 2: return r.folder
            if col == 3: return str(r.uid)
            if col == 4: return r.date
            if col == 5: return r.from_
            if col == 6: return r.subject
            if col == 7: return ", ".join(r.hit_keywords)
            if col == 8: return ", ".join(r.hit_synonym)
            if col == 9: return ", ".join(r.hit_fields)
            if col == 10: return r.hit_content
        elif role == Qt.ToolTipRole:
            if col == 5: return r.from_
            if col == 6: return r.subject
            if col == 7: return "\n".join(r.hit_keywords)
            if col == 8: return "\n".join(r.hit_synonym)
            if col == 9: return "\n".join(r.hit_fields)
            if col == 10: return r.hit_content
        return None

    def get_record(self, row: int) -> Optional[HitRecord]:
        if 0 <= row < len(self._records):
            return self._records[row]
        return None

    def all_records(self) -> List[HitRecord]:
        return list(self._records)
