# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 — 邮件关键词审计系统"""

import sys
import os

block_cipher = None

# 收集 conda 环境 Library/bin 里的 DLL（PyInstaller 默认只扫 DLLs/）
import glob as _glob
_LIB_BIN = os.path.join(os.path.dirname(sys.executable), "Library", "bin")
_add_dlls = []
for _f in _glob.glob(os.path.join(_LIB_BIN, "*.dll")):
    _add_dlls.append((_f, "."))

a = Analysis(
    ['main.py'],
    pathex=[os.path.dirname(os.path.abspath(SPEC))],
    binaries=_add_dlls,
    datas=[],
    hiddenimports=[
        'bs4',
        'imaplib',
        'ssl',
        'email',
        'email.utils',
        'email.message',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'numpy',
        'PyQt5',
        'PyQt6',
        'pytest',
        'IPython',
        'pytz',
        'nose',
    ],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='EmailAudit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # 不启用 UPX，避免杀毒误报
    runtime_tmpdir=None,
    console=False,           # 不显示命令行窗口
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/logo.ico',
)
