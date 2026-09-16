#!/usr/bin/env python
"""邮箱关键词审计系统 — 入口"""
import sys
import os

# 确保项目根目录在 sys.path 最前面（解决从任意目录启动都能 import src 的问题）
if getattr(sys, "frozen", False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = os.path.dirname(os.path.abspath(__file__))
# 用绝对路径 + 插入最前，优先级高于 cwd
sys.path.insert(0, os.path.abspath(base_path))

# 工作目录也切到项目根（eml 输出等相对路径依赖）
os.chdir(os.path.abspath(base_path))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtCore import Qt

from src.gui.main_window import MainWindow


def detect_dark_mode(app: QApplication) -> bool:
    """用 Qt 自己的 palette 亮度判断是否深色——这是最靠谱的方式"""
    pal = app.palette()
    w = pal.color(QPalette.Window)
    # 把 RGB 转灰度，< 128 就算深色
    gray = 0.299 * w.red() + 0.587 * w.green() + 0.114 * w.blue()
    return gray < 128


def _apply_preset_dark_palette(app: QApplication):
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(30, 30, 30))
    pal.setColor(QPalette.WindowText, QColor(212, 212, 212))
    pal.setColor(QPalette.Base, QColor(37, 37, 38))
    pal.setColor(QPalette.AlternateBase, QColor(45, 45, 45))
    pal.setColor(QPalette.Text, QColor(212, 212, 212))
    pal.setColor(QPalette.Button, QColor(60, 60, 60))
    pal.setColor(QPalette.ButtonText, QColor(212, 212, 212))
    pal.setColor(QPalette.Highlight, QColor(0, 122, 204))
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(96, 96, 96))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(96, 96, 96))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(96, 96, 96))
    app.setPalette(pal)


def _apply_preset_light_palette(app: QApplication):
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(252, 252, 252))
    pal.setColor(QPalette.WindowText, QColor(32, 32, 32))
    pal.setColor(QPalette.Base, QColor(255, 255, 255))
    pal.setColor(QPalette.AlternateBase, QColor(245, 247, 250))
    pal.setColor(QPalette.Text, QColor(32, 32, 32))
    pal.setColor(QPalette.Button, QColor(245, 245, 245))
    pal.setColor(QPalette.ButtonText, QColor(32, 32, 32))
    pal.setColor(QPalette.Highlight, QColor(0, 102, 204))
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(145, 145, 145))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(145, 145, 145))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(145, 145, 145))
    app.setPalette(pal)


# ========== 深色主题 ==========
GLOBAL_QSS_DARK = """
/* ===== 基础 ===== */
QMainWindow, QDialog, QMessageBox { background-color: #1E1E1E; }
/* 关键：不给 QWidget transparent，让所有 widget 都实底，不露出 DWM 深色 */
QWidget { background-color: #1E1E1E; color: #D4D4D4; }
QMenuBar { background-color: #1E1E1E; color: #D4D4D4; border: none; height: 0; max-height: 0; }
QStatusBar { background-color: #1E1E1E; color: #D4D4D4; border: none; height: 0; max-height: 0; }
QMessageBox QLabel { color: #D4D4D4; background: transparent; }
QMessageBox QPushButton { min-width: 80px; }

/* ===== 分组 ===== */
QGroupBox {
    font-size: 13px; font-weight: bold;
    border: 1px solid #3C3C3C; border-radius: 6px;
    margin-top: 14px; padding: 16px 14px 10px 14px;
    background-color: #252526;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 12px; top: -2px; padding: 0 8px;
    color: #D4D4D4; background-color: #252526;
    font-size: 13px; font-weight: bold;
}

/* ===== 标签页 ===== */
QTabWidget::pane {
    border: 1px solid #3C3C3C; border-radius: 6px;
    background-color: #252526; top: -1px;
}
QTabBar::tab {
    padding: 7px 20px; font-size: 13px;
    border: 1px solid #3C3C3C; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
    margin-right: 2px;
    background-color: #2D2D2D; color: #858585;
}
QTabBar::tab:selected { background-color: #1E1E1E; color: #007ACC; font-weight: bold; }
QTabBar::tab:hover:!selected { color: #D4D4D4; }

/* ===== 按钮 ===== */
QPushButton {
    padding: 6px 18px; font-size: 13px;
    border: 1px solid #3C3C3C; border-radius: 4px;
    background-color: #3C3C3C; color: #D4D4D4; min-height: 22px;
}
QPushButton:hover { background-color: #4C4C4C; }
QPushButton:pressed { background-color: #007ACC; color: white; border-color: #007ACC; }
QPushButton:disabled { background-color: #2D2D2D; color: #606060; }

/* 主操作按钮 */
QPushButton#btnPrimary {
    background-color: #007ACC; color: white; border: none;
    font-size: 14px; font-weight: bold;
    padding: 8px 28px; border-radius: 5px;
}
QPushButton#btnPrimary:hover { background-color: #0062A3; }
QPushButton#btnPrimary:pressed { background-color: #007ACC; }
QPushButton#btnPrimary:disabled { background-color: #3C3C3C; color: #606060; }

/* ===== 输入 ===== */
QDateEdit, QSpinBox, QLineEdit, QPlainTextEdit, QTextEdit {
    padding: 5px 8px; font-size: 13px;
    background-color: #3C3C3C; color: #D4D4D4;
    border: 1px solid #3C3C3C; border-radius: 4px;
    selection-background-color: #007ACC; selection-color: white;
}
QDateEdit:focus, QSpinBox:focus, QLineEdit:focus,
QPlainTextEdit:focus, QTextEdit:focus { border-color: #007ACC; }

QComboBox {
    padding: 5px 8px; font-size: 13px;
    background-color: #3C3C3C; color: #D4D4D4;
    border: 1px solid #3C3C3C; border-radius: 4px; min-height: 22px;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background-color: #252526; color: #D4D4D4;
    selection-background-color: #007ACC; selection-color: white;
    border: 1px solid #3C3C3C;
}

/* ===== 日历内部 ===== */
QCalendarWidget QTableView {
    background-color: #1E1E1E; alternate-background-color: #1E1E1E;
    selection-background-color: #007ACC; selection-color: white;
    gridline-color: transparent; border: none; font-size: 12px;
}
QCalendarWidget QTableView::item { padding: 2px; color: #D4D4D4; }
QCalendarWidget QTableView::item:selected { background-color: #007ACC; color: white; }
QCalendarWidget QHeaderView::section {
    background-color: #1E1E1E; color: #D4D4D4; border: none; padding: 4px; font-weight: normal;
}

/* ===== 勾选/单选 ===== */
QCheckBox, QRadioButton { color: #D4D4D4; spacing: 6px; font-size: 13px; }

/* ===== 标签 ===== */
QLabel { color: #D4D4D4; background: transparent; font-size: 13px; }

/* ===== 表格 ===== */
QTableView {
    gridline-color: #3C3C3C; font-size: 13px;
    background-color: #252526; color: #D4D4D4;
    selection-background-color: #007ACC; selection-color: white;
    alternate-background-color: #2D2D2D;
    border: 1px solid #3C3C3C; border-radius: 4px;
}
QTableView::item { padding: 3px 8px; }
QHeaderView::section {
    background-color: #3C3C3C; color: #D4D4D4; font-weight: bold; font-size: 13px;
    padding: 7px; border: none; border-right: 1px solid #3C3C3C;
}
QHeaderView::section:last { border-right: none; }

/* ===== 进度条 ===== */
QProgressBar {
    border: 1px solid #3C3C3C; border-radius: 8px; text-align: center;
    height: 24px; background-color: #252526; color: #D4D4D4; font-size: 12px;
}
QProgressBar::chunk { background-color: #007ACC; border-radius: 7px; }

/* ===== 日志 ===== */
QPlainTextEdit#logText {
    font-family: Consolas, 'Courier New', monospace; font-size: 12px;
    background-color: #1E1E1E; color: #D4D4D4;
    border: 1px solid #3C3C3C; border-radius: 4px; padding: 6px;
}

/* ===== 滚动条 ===== */
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background-color: #424242; border-radius: 4px; min-height: 20px; }
QScrollBar::handle:vertical:hover { background-color: #007ACC; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 8px; }
QScrollBar::handle:horizontal { background-color: #424242; border-radius: 4px; min-width: 20px; }
QScrollBar::handle:horizontal:hover { background-color: #007ACC; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
"""


# ========== 浅色主题 ==========
GLOBAL_QSS_LIGHT = """
/* ===== 基础 ===== */
QMainWindow, QDialog, QMessageBox { background-color: #FCFCFC; }
/* 关键：不给 QWidget transparent，让所有 widget 都实底，不露出 DWM 深色 */
QWidget { background-color: #FCFCFC; color: #202020; }
QMenuBar { background-color: #FCFCFC; color: #202020; border: none; height: 0; max-height: 0; }
QStatusBar { background-color: #FCFCFC; color: #202020; border: none; height: 0; max-height: 0; }
QMessageBox QLabel { color: #202020; background: transparent; }
QMessageBox QPushButton { min-width: 80px; }

/* ===== 分组 ===== */
QGroupBox {
    font-size: 13px; font-weight: bold;
    border: 1px solid #D2D2D2; border-radius: 6px;
    margin-top: 14px; padding: 16px 14px 10px 14px;
    background-color: #FFFFFF;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 12px; top: -2px; padding: 0 8px;
    color: #202020; background-color: #FFFFFF;
    font-size: 13px; font-weight: bold;
}

/* ===== 标签页 ===== */
QTabWidget::pane {
    border: 1px solid #D2D2D2; border-radius: 6px;
    background-color: #FFFFFF; top: -1px;
}
QTabBar::tab {
    padding: 7px 20px; font-size: 13px;
    border: 1px solid #D2D2D2; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
    margin-right: 2px;
    background-color: #FCFCFC; color: #919191;
}
QTabBar::tab:selected { background-color: #FFFFFF; color: #0066CC; font-weight: bold; }
QTabBar::tab:hover:!selected { color: #202020; }

/* ===== 按钮 ===== */
QPushButton {
    padding: 6px 18px; font-size: 13px;
    border: 1px solid #D2D2D2; border-radius: 4px;
    background-color: #F5F5F5; color: #202020; min-height: 22px;
}
QPushButton:hover { background-color: #D2D2D2; }
QPushButton:pressed { background-color: #0066CC; color: white; border-color: #0066CC; }
QPushButton:disabled { background-color: #FCFCFC; color: #919191; }

/* 主操作按钮 */
QPushButton#btnPrimary {
    background-color: #0066CC; color: white; border: none;
    font-size: 14px; font-weight: bold;
    padding: 8px 28px; border-radius: 5px;
}
QPushButton#btnPrimary:hover { background-color: #0050A0; }
QPushButton#btnPrimary:pressed { background-color: #0066CC; }
QPushButton#btnPrimary:disabled { background-color: #D2D2D2; color: #919191; }

/* ===== 输入 ===== */
QDateEdit, QSpinBox, QLineEdit, QPlainTextEdit, QTextEdit {
    padding: 5px 8px; font-size: 13px;
    background-color: #FFFFFF; color: #202020;
    border: 1px solid #D2D2D2; border-radius: 4px;
    selection-background-color: #0066CC; selection-color: white;
}
QDateEdit:focus, QSpinBox:focus, QLineEdit:focus,
QPlainTextEdit:focus, QTextEdit:focus { border-color: #0066CC; }

QComboBox {
    padding: 5px 8px; font-size: 13px;
    background-color: #FFFFFF; color: #202020;
    border: 1px solid #D2D2D2; border-radius: 4px; min-height: 22px;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background-color: #FFFFFF; color: #202020;
    selection-background-color: #0066CC; selection-color: white;
    border: 1px solid #D2D2D2;
}

/* ===== 日历内部 ===== */
QCalendarWidget QTableView {
    background-color: #FCFCFC; alternate-background-color: #FCFCFC;
    selection-background-color: #0066CC; selection-color: white;
    gridline-color: transparent; border: none; font-size: 12px;
}
QCalendarWidget QTableView::item { padding: 2px; color: #202020; }
QCalendarWidget QTableView::item:selected { background-color: #0066CC; color: white; }
QCalendarWidget QHeaderView::section {
    background-color: #FCFCFC; color: #202020; border: none; padding: 4px; font-weight: normal;
}

/* ===== 勾选/单选 ===== */
QCheckBox, QRadioButton { color: #202020; spacing: 6px; font-size: 13px; }

/* ===== 标签 ===== */
QLabel { color: #202020; background: transparent; font-size: 13px; }

/* ===== 表格 ===== */
QTableView {
    gridline-color: #D2D2D2; font-size: 13px;
    background-color: #FFFFFF; color: #202020;
    selection-background-color: #0066CC; selection-color: white;
    alternate-background-color: #F5F7FA;
    border: 1px solid #D2D2D2; border-radius: 4px;
}
QTableView::item { padding: 3px 8px; }
QHeaderView::section {
    background-color: #F5F5F5; color: #202020; font-weight: bold; font-size: 13px;
    padding: 7px; border: none; border-right: 1px solid #D2D2D2;
}
QHeaderView::section:last { border-right: none; }

/* ===== 进度条 ===== */
QProgressBar {
    border: 1px solid #D2D2D2; border-radius: 8px; text-align: center;
    height: 24px; background-color: #FFFFFF; color: #202020; font-size: 12px;
}
QProgressBar::chunk { background-color: #0066CC; border-radius: 7px; }

/* ===== 日志 ===== */
QPlainTextEdit#logText {
    font-family: Consolas, 'Courier New', monospace; font-size: 12px;
    background-color: #FFFFFF; color: #202020;
    border: 1px solid #D2D2D2; border-radius: 4px; padding: 6px;
}

/* ===== 滚动条 ===== */
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background-color: #D2D2D2; border-radius: 4px; min-height: 20px; }
QScrollBar::handle:vertical:hover { background-color: #0066CC; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 8px; }
QScrollBar::handle:horizontal { background-color: #D2D2D2; border-radius: 4px; min-width: 20px; }
QScrollBar::handle:horizontal:hover { background-color: #0066CC; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
"""


def apply_dark_titlebar(hwnd: int, dark: bool):
    """用 Windows API 让窗口标题栏匹配主题"""
    try:
        import ctypes
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(ctypes.c_int(1 if dark else 0)), 4,
        )
    except Exception:
        pass


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("邮箱关键词审计系统")
    app.setOrganizationName("EmailAudit")
    app.setFont(QFont("Microsoft YaHei UI", 10))

    # ===== 关键：先检测再 setStyle =====
    # setStyle("Fusion") 在 PySide6 6.x 会偷偷改 palette 为深色，
    # 所以必须在它之前查原始 palette 的亮度
    is_dark = detect_dark_mode(app)
    print(f"[DEBUG] is_dark={is_dark}, Qt.Window before setStyle="
          f"{app.palette().color(QPalette.ColorRole.Window).getRgb()}")

    # 强制 Fusion 风格（绕开 qwindows/qmodernwindowsstyle 插件）
    app.setStyle("Fusion")

    # Fusion 改坏了 palette，再手动盖回系统主题对应的 palette
    if is_dark:
        _apply_preset_dark_palette(app)
    else:
        _apply_preset_light_palette(app)

    qss = GLOBAL_QSS_DARK if is_dark else GLOBAL_QSS_LIGHT
    app.setStyleSheet(qss)

    # 监听系统主题切换（Windows 深色/浅色模式切换时自动刷新）
    try:
        def _on_scheme(scheme):
            if scheme == Qt.ColorScheme.Dark:
                _apply_preset_dark_palette(app)
                app.setStyleSheet(GLOBAL_QSS_DARK)
                try:
                    apply_dark_titlebar(int(app.activeWindow().winId() if app.activeWindow() else 0), True)
                except Exception:
                    pass
            else:
                _apply_preset_light_palette(app)
                app.setStyleSheet(GLOBAL_QSS_LIGHT)
                try:
                    apply_dark_titlebar(int(app.activeWindow().winId() if app.activeWindow() else 0), False)
                except Exception:
                    pass
        app.styleHints().colorSchemeChanged.connect(_on_scheme)
    except Exception:
        pass

    window = MainWindow()
    window.show()

    # 标题栏颜色跟随主题
    apply_dark_titlebar(int(window.winId()), is_dark)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
