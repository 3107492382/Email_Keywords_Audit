"""审计结果记录模型"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class HitRecord:
    """单封命中邮件的记录"""
    account: str            # 邮箱账号
    uid: int                # IMAP UID
    date: str               # 邮件日期
    from_: str              # 发件人
    to: str                 # 收件人
    subject: str            # 主题
    account_name: str = ""  # 账号姓名（前端填写的）
    folder: str = ""        # 文件夹
    cc: str = ""            # 抄送
    hit_keywords: List[str] = field(default_factory=list)
    hit_fields: List[str] = field(default_factory=list)
    hit_content: str = ""
    eml_path: str = ""


@dataclass
class AccountStat:
    """单账号统计"""
    email: str
    name: str = ""
    hit_count: int = 0
    hit_keywords: List[str] = field(default_factory=list)
    scanned_folders: List[str] = field(default_factory=list)
    skipped_folders: List[str] = field(default_factory=list)


@dataclass
class AuditResult:
    """整体审计结果"""
    records: List[HitRecord] = field(default_factory=list)
    failures: Dict[str, str] = field(default_factory=dict)
    account_stats: Dict[str, AccountStat] = field(default_factory=dict)

    def add_record(self, r: HitRecord):
        self.records.append(r)
        stat = self.account_stats.setdefault(r.account, AccountStat(email=r.account, name=r.account_name))
        # 如果 stat 已存在但 name 为空，补上
        if not stat.name and r.account_name:
            stat.name = r.account_name
        stat.hit_count += 1
        for kw in r.hit_keywords:
            if kw not in stat.hit_keywords:
                stat.hit_keywords.append(kw)
        if r.folder not in stat.scanned_folders:
            stat.scanned_folders.append(r.folder)

    def add_failure(self, email: str, error: str):
        self.failures[email] = error

    def add_skipped_folder(self, email: str, folder: str):
        stat = self.account_stats.setdefault(email, AccountStat(email=email))
        if folder not in stat.skipped_folders:
            stat.skipped_folders.append(folder)

    def total_hits(self) -> int:
        return len(self.records)
