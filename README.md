# 邮箱关键词审计系统

基于 PySide6 的桌面端邮件关键词审计工具，通过 IMAP 协议批量扫描多个邮箱账号中的邮件，按关键词命中规则筛选并导出为 Excel 汇总表与 .eml 原始邮件归档。

## 功能特性

### 邮箱扫描
- 支持 QQ 邮箱、腾讯企业邮箱（标准版/海外版/信创版）及自定义 IMAP 服务器一键切换
- 扫描范围覆盖收件箱、已发送、草稿、已删除等所有邮箱文件夹
- UTF-7 编码的自定义文件夹自动解码为中文名显示
- 按时间范围（起止日期）过滤邮件，使用 RFC822 标准日期格式
- 多账号并发扫描（1-5 个线程可配），支持账号失败自动重试

### 关键词匹配
- 统一 substring 子串匹配，中英文关键词通用，无需区分模式
- 检索范围覆盖 6 个字段：主题、发件人、收件人、抄送、正文、附件名
- 命中内容提取：按句号/问号/感叹号/换行符切分，抽取关键词所在完整句子作为命中上下文
- 支持区分大小写选项

### 账号管理
- 单账号添加、批量 CSV 导入、编辑、删除
- 账号信息使用 Fernet 对称加密存储，密钥由本机特征（MAC 地址、计算机名、用户名）派生，无需密码输入
- 账号列表显示行号，支持按姓名归档命中邮件

### 数据导出
- Excel 双 Sheet 汇总：
  - Sheet1「命中汇总」：每行一条命中记录，含姓名、账号、文件夹、UID、日期、发件人、收件人、抄送、主题、命中关键词、命中字段、命中内容、EML 路径
  - Sheet2「按账号统计」：按账号汇总命中邮件数、命中关键词、命中的文件夹
  - 列宽自适应：中文按 2 字符、英文按 1 字符计算，限制在 8-55 之间
- 邮件归档目录结构：
  - `output/[时间戳]/全部邮件/[账号]/[文件夹]/[UID].eml` 原始邮件
  - `output/[时间戳]/命中邮件/[姓名]/[文件夹]/[UID].eml` 命中邮件副本
  - `output/[时间戳]/关键词检索命中记录.xlsx` 汇总表
- 时间字段统一格式 `YYYY-MM-DD HH:MM:SS`

### GUI 交互
- 深色/浅色主题自动跟随系统，切换实时生效
- 全部界面元素可点击，无命令行操作
- Tab 页布局：审计配置、进度日志、命中预览、审计历史
- 命中预览表格列宽可拖动调整
- 文件夹列表点击「测试连接」后从服务器拉取，不预置默认项

## 技术栈

| 组件 | 说明 |
|------|------|
| Python 3.10 | 运行时 |
| PySide6 6.7.0 | GUI 框架 |
| openpyxl 3.1.5 | Excel 读写 |
| beautifulsoup4 4.12.3 | HTML 正文解析 |
| cryptography 43.0.0 | 账号信息加密 |
| imaplib（标准库） | IMAP 协议客户端 |
| PyInstaller | 打包为独立 exe |

## 项目结构

```
email_keywords_audit/
├── main.py                     # 入口，主题与 QSS 初始化
├── run.bat                     # Conda 环境一键运行脚本
├── build.bat                   # PyInstaller 打包脚本
├── build.spec                  # PyInstaller 配置
├── requirements.txt            # 依赖列表
├── assets/                     # 图标等资源
└── src/
    ├── config/
    │   ├── config_manager.py   # config.json 读写，服务器预设
    │   ├── accounts_store.py   # 账号列表存储
    │   └── crypto.py           # 基于机器特征的加解密
    ├── core/
    │   ├── imap_client.py      # IMAP 客户端封装（只读）
    │   ├── mail_parser.py      # 邮件原文解析
    │   ├── keyword_matcher.py  # 关键词匹配与命中内容提取
    │   ├── eml_exporter.py     # .eml 文件落盘
    │   └── excel_exporter.py   # Excel 双 Sheet 导出
    ├── gui/
    │   ├── main_window.py      # 主窗口
    │   ├── accounts_dialog.py  # 账号管理对话框
    │   ├── keywords_editor.py  # 关键词编辑器
    │   └── result_model.py     # 命中预览表格模型
    ├── models/
    │   ├── account.py          # 账号数据类
    │   └── records.py          # 命中记录与统计模型
    └── workers/
        ├── audit_worker.py     # 后台审计线程
        └── retry.py            # 重试装饰器
```

## 部署方式

### 方式一：源码运行（推荐开发调试）

前置条件：已安装 Anaconda 或 Miniconda。

1. 克隆/解压项目到任意目录
2. 双击 `run.bat`，脚本会自动：
   - 检查 conda 是否可用
   - 创建名为 `email_audit` 的 Python 3.10 环境（首次运行）
   - 安装 `requirements.txt` 中的依赖
   - 启动 `python main.py`

也可手动执行：

```powershell
conda create -n email_audit python=3.10 -y
conda activate email_audit
pip install -r requirements.txt
python main.py
```

### 方式二：打包为独立 exe（推荐分发）

1. 双击 `build.bat`，脚本会：
   - 自动查找 conda 环境 `email_audit` 中的 python.exe（或系统 Python）
   - 自动安装 PyInstaller 与依赖（如缺失）
   - 执行 `PyInstaller --noconfirm --clean build.spec`
2. 打包完成后，`dist\EmailAudit.exe` 即为可分发文件
3. 运行时输出目录定位在 exe 所在目录下的 `output/`，不依赖临时目录

打包注意事项：
- `build.spec` 已配置收集 conda `Library/bin` 下的 DLL（libssl/libcrypto），避免 `imaplib.IMAP4_SSL` 缺失
- 未启用 UPX，避免杀毒软件误报
- 以 `console=False` 模式打包，运行时不显示命令行窗口

## 配置与数据存储

应用运行时不使用数据库，所有数据以文件形式存储：

| 文件 | 路径 | 说明 |
|------|------|------|
| 配置文件 | `%APPDATA%\email_audit\config.json` | 服务器参数、扫描文件夹、时间范围、关键词列表 |
| 账号文件 | `%APPDATA%\email_audit\accounts.enc` | Fernet 加密的账号列表 |
| 审计输出 | exe 同级 `output\[时间戳]\` | .eml 邮件归档与 Excel 汇总表 |

如需重置本地数据：删除 `%APPDATA%\email_audit` 目录即可。

## 使用流程

1. 打开应用，在「审计配置」Tab 选择邮箱类型（默认腾讯企业邮箱）
2. 填写 IMAP 主机/端口（预设值会自动填充），点击「测试连接并列出文件夹」
3. 勾选需要扫描的文件夹
4. 设置时间范围、并发数
5. 点击「编辑关键词」录入关键词（每行一个）
6. 点击「账号管理」添加邮箱账号（邮箱地址 + IMAP 授权码 + 姓名）
7. 点击「开始审计」，在「进度日志」Tab 查看实时状态
8. 审计完成后在「命中预览」Tab 查看命中记录，或到 `output\[时间戳]\` 目录查看导出文件
