"""配置管理 — config.json 读写"""
import json
import os
from datetime import date
from pathlib import Path
from typing import List, Optional

# 腾讯企业邮箱服务器预设
SERVER_PRESETS = {
    "标准版": {"host": "imap.exmail.qq.com", "port": 993, "use_ssl": True},
    "海外版": {"host": "hwimap.exmail.qq.com", "port": 993, "use_ssl": True},
    "信创版": {"host": "xcimap.exmail.qq.com", "port": 993, "use_ssl": True},
}

# 默认扫描文件夹映射（英文 IMAP 名 -> 中文显示名）
DEFAULT_FOLDERS = ["INBOX", "Sent Messages", "Drafts", "Deleted Messages"]
JUNK_FOLDER = "Junk"


class Config:
    """运行配置"""

    def __init__(self):
        self.server_key = "腾讯企业邮箱"   # QQ邮箱（免费）/ 腾讯企业邮箱 / 自定义
        self.audit_mode = "online"          # online=在线审计 / local=本地审计
        self.local_dir = ""                 # 本地审计的邮件根目录（账号目录的上一级）
        self.host = "imap.exmail.qq.com"
        self.port = 993
        self.use_ssl = True
        self.scan_folders = list(DEFAULT_FOLDERS)
        self.include_junk = False
        self.junk_folder = "垃圾邮件"
        self.match_mode = "phrase"
        self.case_sensitive = False
        self.date_start = date.today().replace(day=1).isoformat()
        self.date_end = date.today().isoformat()
        self.max_workers = 2
        self.keywords: List[str] = []
        self.keyword_category: dict = {}   # 主词 → 词汇类别（如 财务相关/业务相关）

    def to_dict(self) -> dict:
        return {
            "server_key": self.server_key,
            "audit_mode": self.audit_mode,
            "local_dir": self.local_dir,
            "host": self.host,
            "port": self.port,
            "use_ssl": self.use_ssl,
            "scan_folders": self.scan_folders,
            "include_junk": self.include_junk,
            "junk_folder": self.junk_folder,
            "match_mode": self.match_mode,
            "case_sensitive": self.case_sensitive,
            "date_start": self.date_start,
            "date_end": self.date_end,
            "max_workers": self.max_workers,
            "keywords": self.keywords,
            "keyword_category": self.keyword_category,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        c = cls()
        c.server_key = d.get("server_key", "腾讯企业邮箱")
        c.audit_mode = d.get("audit_mode", "online")
        c.local_dir = d.get("local_dir", "")
        c.host = d.get("host", "imap.exmail.qq.com")
        c.port = d.get("port", 993)
        c.use_ssl = d.get("use_ssl", True)
        c.scan_folders = d.get("scan_folders", list(DEFAULT_FOLDERS))
        c.include_junk = d.get("include_junk", False)
        c.junk_folder = d.get("junk_folder", "Junk")
        c.match_mode = d.get("match_mode", "phrase")
        c.case_sensitive = d.get("case_sensitive", False)
        c.date_start = d.get("date_start", date.today().replace(day=1).isoformat())
        c.date_end = d.get("date_end", date.today().isoformat())
        c.max_workers = d.get("max_workers", 2)
        c.keywords = d.get("keywords", [])
        raw_cat = d.get("keyword_category", {})
        # 仅保留键值均为非空字符串的映射
        c.keyword_category = (
            {str(k).strip(): str(v).strip()
             for k, v in raw_cat.items()
             if str(k).strip() and str(v).strip()}
            if isinstance(raw_cat, dict) else {}
        )
        return c


class ConfigManager:
    """config.json 读写"""

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
            base_dir = Path(appdata) / "email_audit"
        base_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = base_dir / "config.json"

    def load(self) -> Config:
        if not self.file_path.exists():
            cfg = Config()
            self.save(cfg)
            return cfg
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
            return Config.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            # 损坏则备份并重建
            backup = self.file_path.with_suffix(".json.bak")
            try:
                self.file_path.rename(backup)
            except Exception:
                pass
            cfg = Config()
            self.save(cfg)
            return cfg

    def save(self, config: Config) -> None:
        self.file_path.write_text(
            json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
