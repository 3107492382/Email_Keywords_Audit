"""审计任务 Worker — QThread 后台并发检索"""
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QThread, Signal

from src.core.eml_exporter import EmlExporter
from src.core.imap_client import FolderNotFoundError, ImapClient, ImapError
from src.core.keyword_matcher import KeywordMatcher
from src.core.mail_parser import MailParser
from src.models.account import Account
from src.models.records import AuditResult, HitRecord
from src.workers.retry import retry


@dataclass
class AccountAuditResult:
    """单账号审计结果"""
    records: List[HitRecord] = field(default_factory=list)
    skipped_folders: List[str] = field(default_factory=list)
    error: Optional[str] = None


class AuditWorker(QThread):
    """后台审计线程"""

    progress = Signal(int, int, str)       # current, total, message
    account_started = Signal(str)          # email
    account_done = Signal(str, int)        # email, hit_count
    account_failed = Signal(str, str)      # email, error
    folder_done = Signal(str, str, int)    # email, folder, hits_in_folder
    log = Signal(str)                       # 日志消息
    finished_ok = Signal(object)           # AuditResult

    def __init__(self, accounts: List[Account], keywords: List[str],
                 date_start: date, date_end: date,
                 host: str, port: int, use_ssl: bool,
                 scan_folders: List[str], include_junk: bool, match_mode: str,
                 case_sensitive: bool, junk_folder: str = "Junk",
                 folder_labels: Optional[Dict[str, str]] = None,
                 max_workers: int = 2,
                 output_dir: Optional[Path] = None,
                 synonyms: Optional[Dict[str, list]] = None,
                 parent=None):
        super().__init__(parent)
        self.accounts = accounts
        self.keywords = keywords
        self.date_start = date_start
        self.date_end = date_end
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.scan_folders = scan_folders
        self.include_junk = include_junk
        self.junk_folder = junk_folder
        self.folder_labels = folder_labels or {}   # IMAP raw → 中文显示名
        self.match_mode = match_mode
        self.case_sensitive = case_sensitive
        self.max_workers = max(1, min(max_workers, 5))
        self.output_dir = output_dir or Path("output")
        self.synonyms = synonyms or {}
        self._cancel = threading.Event()

    def _display(self, raw_folder: str) -> str:
        """IMAP 原始名 → 中文显示名（找不到则返回原始名）"""
        return self.folder_labels.get(raw_folder, raw_folder)

    def cancel(self):
        self._cancel.set()

    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    def run(self):
        result = AuditResult()
        total = len(self.accounts)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_base = self.output_dir / ts / "全部邮件"
        out_base.mkdir(parents=True, exist_ok=True)

        matcher = KeywordMatcher(self.keywords, self.case_sensitive, self.synonyms)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_map = {
                executor.submit(self._audit_one, acc, matcher, out_base): acc
                for acc in self.accounts
            }

            for i, fut in enumerate(as_completed(future_map), 1):
                if self.is_cancelled():
                    break
                acc = future_map[fut]
                try:
                    acc_result = fut.result()
                    # 合并记录
                    for r in acc_result.records:
                        result.add_record(r)
                    # 合并跳过的文件夹
                    for sf in acc_result.skipped_folders:
                        result.add_skipped_folder(acc.email, sf)

                    self.account_done.emit(acc.email, len(acc_result.records))
                except Exception as e:
                    err_msg = f"{type(e).__name__}: {e}"
                    result.add_failure(acc.email, err_msg)
                    self.account_failed.emit(acc.email, err_msg)

                self.progress.emit(i, total, f"已完成 {i}/{total}")

        self.finished_ok.emit(result)

    def _audit_one(self, account: Account, matcher: KeywordMatcher,
                   out_base: Path) -> AccountAuditResult:
        """审计单个账号"""
        acc_result = AccountAuditResult()

        if self.is_cancelled():
            return acc_result

        self.account_started.emit(account.email)
        self.log.emit(f"[{account.email}] 开始连接 {self.host}:{self.port} ...")

        client = ImapClient(host=self.host, port=self.port, use_ssl=self.use_ssl)

        # 连接重试
        try:
            @retry((ImapError, OSError), tries=3, delay=1, backoff=2)
            def _connect():
                client.connect(account.email, account.auth_code)

            _connect()
            self.log.emit(f"[{account.email}] 连接成功")
        except Exception as e:
            client.logout()
            self.log.emit(f"[{account.email}] 连接失败: {e}")
            raise

        folders = list(self.scan_folders)
        if self.include_junk and self.junk_folder:
            folders.append(self.junk_folder)

        try:
            for raw_folder in folders:
                if self.is_cancelled():
                    break
                display = self._display(raw_folder)   # 中文显示名
                try:
                    # IMAP 操作用 raw name
                    uids = client.search_uids(raw_folder, self.date_start, self.date_end)
                    self.log.emit(f"[{account.email}] {display}: {len(uids)} 封在时间范围内")

                    folder_hits = 0
                    folder_total = len(uids)
                    folder_done = 0
                    for uid, raw in client.fetch_batch(uids):
                        if self.is_cancelled():
                            break
                        folder_done += 1
                        if folder_done % 10 == 0 or folder_done == folder_total:
                            self.log.emit(f"[{account.email}] {display}: 已处理 {folder_done}/{folder_total}")
                        try:
                            parsed = MailParser.parse(raw)
                            # 全部存 .eml（已拉取，顺手落盘零成本）
                            # 目录名用中文名 display
                            eml_path = EmlExporter.save(
                                raw, account.email, display, uid, out_base,
                                account_name=account.name or account.email,
                            )
                            hit_kws, hit_fields, hit_content, hit_synonym = matcher.match_record(parsed)
                            if hit_kws:
                                acc_result.records.append(HitRecord(
                                    account=account.email,
                                    account_name=account.name or account.email,
                                    folder=display,       # 命中记录里存中文名
                                    uid=uid,
                                    date=parsed.date,
                                    from_=parsed.from_,
                                    to=parsed.to,
                                    cc=parsed.cc,
                                    subject=parsed.subject,
                                    hit_keywords=hit_kws,
                                    hit_fields=hit_fields,
                                    hit_content=hit_content,
                                    hit_synonym=hit_synonym,
                                    eml_path=str(eml_path),
                                ))
                                folder_hits += 1
                        except Exception as e:
                            self.log.emit(f"[{account.email}] {display} UID={uid} 解析失败: {e}")

                    self.folder_done.emit(account.email, display, folder_hits)
                except FolderNotFoundError:
                    self.log.emit(f"[{account.email}] 文件夹 {display} 不存在，跳过")
                    acc_result.skipped_folders.append(display)
                except Exception as e:
                    self.log.emit(f"[{account.email}] {display} 检索失败: {e}")
        finally:
            client.logout()
            self.log.emit(f"[{account.email}] 已断开")

        return acc_result
