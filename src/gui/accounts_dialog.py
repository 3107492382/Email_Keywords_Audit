"""账号管理对话框 — 全前端可配置（增/删/改/CSV导入）"""
import csv
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox, QLabel,
    QLineEdit, QFormLayout, QGroupBox, QHeaderView,
)

from src.config.accounts_store import AccountsStore
from src.config.crypto import CryptoError
from src.models.account import Account


class AccountsDialog(QDialog):
    """账号管理对话框 — 全前端可配置"""

    def __init__(self, store: AccountsStore, parent=None):
        super().__init__(parent)
        self.setWindowTitle("账号管理")
        self.resize(800, 600)
        self.store = store
        self._accounts: List[Account] = []

        self._load_accounts()
        self._build_ui()
        self._refresh_table()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 顶部信息
        info = QLabel(f"已配置 {len(self._accounts)} 个邮箱账号")
        info.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 4px;")
        self._info_label = info
        layout.addWidget(info)

        # ====== 添加账号表单 ======
        add_group = QGroupBox("添加新账号")
        add_form = QFormLayout(add_group)
        add_form.setSpacing(6)

        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("如：张三（可选）")
        add_form.addRow("姓名:", self.input_name)

        self.input_email = QLineEdit()
        self.input_email.setPlaceholderText("如：zhangsan@company.com")
        add_form.addRow("邮箱地址:", self.input_email)

        self.input_auth = QLineEdit()
        self.input_auth.setEchoMode(QLineEdit.Password)
        self.input_auth.setPlaceholderText("邮箱客户端授权码")
        add_form.addRow("授权码:", self.input_auth)

        add_btn_row = QHBoxLayout()
        self.btn_add = QPushButton("添加到列表")
        self.btn_add.setDefault(True)
        self.btn_add.clicked.connect(self._add_one)
        add_btn_row.addStretch()
        add_btn_row.addWidget(self.btn_add)
        add_form.addRow("", add_btn_row)

        layout.addWidget(add_group)

        # ====== 已配置账号表格 ======
        table_group = QGroupBox("已配置账号（双击单元格可直接编辑）")
        table_layout = QVBoxLayout(table_group)
        table_layout.setContentsMargins(8, 8, 8, 8)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["姓名", "邮箱地址", "授权码"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
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

        btn_import = QPushButton("从 CSV 批量导入")
        btn_import.clicked.connect(self._import_csv)
        btn_layout.addWidget(btn_import)

        btn_export = QPushButton("导出 CSV 模板")
        btn_export.clicked.connect(self._export_template)
        btn_layout.addWidget(btn_export)

        btn_layout.addStretch()

        btn_del = QPushButton("删除选中行")
        btn_del.clicked.connect(self._delete_selected)
        btn_layout.addWidget(btn_del)

        btn_clear_all = QPushButton("清空全部")
        btn_clear_all.clicked.connect(self._clear_all)
        btn_layout.addWidget(btn_clear_all)

        btn_layout.addStretch()

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _load_accounts(self):
        try:
            self._accounts = self.store.load()
        except CryptoError:
            # 加密文件损坏或密钥已变 — 静默重置
            try:
                self.store.file_path.unlink(missing_ok=True)
            except Exception:
                pass
            self._accounts = []

    def _refresh_table(self):
        self.table.setRowCount(len(self._accounts))
        for i, acc in enumerate(self._accounts):
            name_item = QTableWidgetItem(acc.name)
            email_item = QTableWidgetItem(acc.email)
            auth_item = QTableWidgetItem()

            # 授权码显示为星号，但保留真实值在 UserRole
            auth_display = "*" * min(len(acc.auth_code), 16) if acc.auth_code else ""
            auth_item.setData(Qt.DisplayRole, auth_display)
            auth_item.setData(Qt.UserRole, acc.auth_code)
            # 授权码列不允许直接编辑（避免误改），如需修改请删除后重新添加
            auth_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

            self.table.setItem(i, 0, name_item)
            self.table.setItem(i, 1, email_item)
            self.table.setItem(i, 2, auth_item)

        self._info_label.setText(f"已配置 {len(self._accounts)} 个邮箱账号")

    def _add_one(self):
        """从表单添加单个账号"""
        name = self.input_name.text().strip()
        email_addr = self.input_email.text().strip()
        auth_code = self.input_auth.text().strip()

        if not email_addr:
            QMessageBox.warning(self, "信息不完整", "请填写邮箱地址")
            self.input_email.setFocus()
            return
        if "@" not in email_addr:
            QMessageBox.warning(self, "邮箱格式错误", "邮箱地址必须包含 @")
            self.input_email.setFocus()
            return
        if not auth_code:
            QMessageBox.warning(self, "信息不完整", "请填写授权码")
            self.input_auth.setFocus()
            return

        # 检查是否已存在
        for acc in self._accounts:
            if acc.email.lower() == email_addr.lower():
                QMessageBox.warning(self, "账号已存在", f"邮箱 {email_addr} 已在列表中")
                return

        self._accounts.append(Account(email=email_addr, auth_code=auth_code, name=name))
        self._refresh_table()
        self._save()

        # 清空表单
        self.input_name.clear()
        self.input_email.clear()
        self.input_auth.clear()
        self.input_name.setFocus()

    def _import_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 CSV 文件", "", "CSV 文件 (*.csv);;所有文件 (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"读取 CSV 失败: {e}")
            return

        added = 0
        skipped = 0
        existing = {acc.email.lower() for acc in self._accounts}
        for row in rows:
            if len(row) < 2:
                continue
            name = row[0].strip()
            email_addr = row[1].strip()
            if not email_addr or "@" not in email_addr:
                continue
            # 跳过表头
            if name.lower() in ("姓名", "name") and email_addr.lower() in ("邮箱", "email", "邮箱地址"):
                continue
            auth_code = row[2].strip() if len(row) >= 3 else ""
            if not auth_code:
                skipped += 1
                continue
            if email_addr.lower() in existing:
                skipped += 1
                continue
            self._accounts.append(Account(email=email_addr, auth_code=auth_code, name=name))
            existing.add(email_addr.lower())
            added += 1

        self._refresh_table()
        self._save()
        msg = f"成功导入 {added} 个账号"
        if skipped:
            msg += f"\n跳过 {skipped} 个（无授权码或已存在）"
        QMessageBox.information(self, "导入完成", msg)

    def _export_template(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存 CSV 模板", "accounts_template.csv", "CSV 文件 (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["姓名", "邮箱地址", "授权码"])
                writer.writerow(["张三", "zhangsan@company.com", "在此填入授权码"])
                writer.writerow(["李四", "lisi@company.com", "在此填入授权码"])
            QMessageBox.information(self, "导出成功", f"模板已保存到:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _delete_selected(self):
        rows = set(idx.row() for idx in self.table.selectedIndexes())
        if not rows:
            QMessageBox.information(self, "提示", "请先选中要删除的行")
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除 {len(rows)} 个账号？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self._accounts = [a for i, a in enumerate(self._accounts) if i not in rows]
        self._refresh_table()
        self._save()

    def _clear_all(self):
        if not self._accounts:
            return
        reply = QMessageBox.question(
            self, "确认清空",
            f"确定要清空全部 {len(self._accounts)} 个账号？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._accounts = []
            self._refresh_table()
            self._save()

    def _collect_from_table(self) -> List[Account]:
        """从表格中收集账号（处理用户对姓名/邮箱的直接编辑）"""
        result = []
        for i in range(self.table.rowCount()):
            name_item = self.table.item(i, 0)
            email_item = self.table.item(i, 1)
            auth_item = self.table.item(i, 2)
            name = name_item.text().strip() if name_item else ""
            email_addr = email_item.text().strip() if email_item else ""
            auth_code = ""
            if auth_item:
                # 优先取 UserRole 中保存的原始值
                auth_code = auth_item.data(Qt.UserRole) or ""
                if not auth_code:
                    # 用户可能直接编辑了星号，取显示文本（极少情况）
                    txt = auth_item.data(Qt.DisplayRole) or ""
                    if txt and not txt.startswith("*"):
                        auth_code = txt.strip()
            if email_addr:
                result.append(Account(email=email_addr, auth_code=auth_code, name=name))
        return result

    def _save(self):
        """立即持久化"""
        try:
            self._accounts = self._collect_from_table()
            self.store.save(self._accounts)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def _save_and_close(self):
        self._save()
        self.accept()

    def get_accounts(self) -> List[Account]:
        return self._accounts
