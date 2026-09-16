"""关键词编辑对话框"""
from pathlib import Path
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QPushButton, QLabel, QFileDialog, QMessageBox,
)


class KeywordsEditor(QDialog):
    """关键词编辑对话框 — 每行一个关键词"""

    def __init__(self, keywords: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑关键词")
        self.resize(500, 400)
        self._keywords = list(keywords)

        layout = QVBoxLayout(self)

        # 提示
        hint = QLabel("每行输入一个关键词，支持中英文混合。保存时会自动去重去空行。")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 13px; margin-bottom: 8px; color: palette(window-text); opacity: 0.7;")
        layout.addWidget(hint)

        # 文本编辑区
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlainText("\n".join(self._keywords))
        self.text_edit.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.text_edit)

        # 按钮行
        btn_layout = QHBoxLayout()

        btn_import_txt = QPushButton("从 .txt 导入")
        btn_import_txt.clicked.connect(self._import_txt)
        btn_layout.addWidget(btn_import_txt)

        btn_layout.addStretch()

        count_label = QLabel(f"当前: {len(self._keywords)} 条")
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

        # 实时计数
        self.text_edit.textChanged.connect(self._update_count)

    def _update_count(self):
        lines = [l.strip() for l in self.text_edit.toPlainText().splitlines() if l.strip()]
        self._count_label.setText(f"当前: {len(set(lines))} 条")

    def _import_txt(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择关键词文件", "", "文本文件 (*.txt);;所有文件 (*)")
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8", errors="replace")
            current = self.text_edit.toPlainText().strip()
            if current:
                self.text_edit.setPlainText(current + "\n" + content)
            else:
                self.text_edit.setPlainText(content)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"读取文件失败: {e}")

    def _clear(self):
        self.text_edit.clear()

    def _save(self):
        lines = self.text_edit.toPlainText().splitlines()
        seen = set()
        result = []
        for line in lines:
            kw = line.strip()
            if kw and kw not in seen:
                seen.add(kw)
                result.append(kw)
        self._keywords = result
        self.accept()

    def get_keywords(self) -> List[str]:
        return self._keywords
