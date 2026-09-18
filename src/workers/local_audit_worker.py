"""本地邮件审计 Worker — 基于已通过 IMAP 拉取落盘的 .eml 文件进行检索

目录结构（与在线审计落盘格式一致）:
    [邮件根目录]/[账号目录]/[文件夹目录]/[UID].eml
其中账号目录名为姓名（未填姓名时为邮箱），文件夹目录名为中文显示名。
"""
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QThread, Signal

from src.core.keyword_matcher import KeywordMatcher
from src.core.mail_parser import MailParser
from src.models.account import Account
from src.models.records import AuditResult, HitRecord


@dataclass
class _AccountTarget:
    """单个本地账号目录的审计任务"""
    email: str              # 账号（目录名或由账号管理映射出的邮箱）
    name: str               # 姓名
    root: Path              # 账号目录
    folders: List[Tuple[str, Path]] = field(default_factory=list)  # (文件夹显示名, 文件夹目录)
    total_files: int = 0


class LocalAuditWorker(QThread):
    """后台本地审计线程（信号与 AuditWorker 保持一致，GUI 可复用同一套槽函数）"""

    progress = Signal(int, int, str)       # current, total, message
    account_started = Signal(str)          # email
    account_done = Signal(str, int)        # email, hit_count
    account_failed = Signal(str, str)      # email, error
    folder_done = Signal(str, str, int)    # email, folder, hits_in_folder
    log = Signal(str)                       # 日志消息
    finished_ok = Signal(object)           # AuditResult

    def __init__(self, source_dir: Path, accounts: List[Account],
                 keywords: List[str], date_start: date, date_end: date,
                 case_sensitive: bool, match_mode: str = "phrase",
                 max_workers: int = 2, output_dir: Optional[Path] = None,
                 synonyms: Optional[dict] = None, export_dir: Optional[Path] = None,
                 categories: Optional[dict] = None,
                 parent=None):
        super().__init__(parent)
        self.source_dir = Path(source_dir)
        self.accounts = accounts
        self.keywords = keywords
        self.categories = categories or {}
        self.date_start = date_start
        self.date_end = date_end
        self.case_sensitive = case_sensitive
        self.match_mode = match_mode
        self.max_workers = max(1, min(max_workers, 5))
        self.output_dir = output_dir or Path("output")
        self.synonyms = synonyms or {}
        # 指定则导出结果（Excel/命中邮件）落到该目录（时间戳目录，与 全部邮件 同级）；
        # 未指定则在 output_dir 下新建时间戳目录
        self.export_dir = Path(export_dir) if export_dir else None
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    # ---- 目录扫描 ----

    def _resolve_account(self, dir_name: str) -> Tuple[str, str]:
        """账号目录名 → (账号, 姓名)
        优先与账号管理中的邮箱/姓名互相映射，失败则目录名同时充当两者
        """
        for acc in self.accounts:
            if acc.email and acc.email == dir_name:
                return acc.email, (acc.name or acc.email)
        for acc in self.accounts:
            if acc.name and acc.name == dir_name:
                return acc.email, acc.name
        return dir_name, dir_name

    def _scan_targets(self) -> List[_AccountTarget]:
        """扫描本地目录，整理出每个账号的待审计文件清单"""
        targets: List[_AccountTarget] = []
        for acc_dir in sorted(self.source_dir.iterdir(), key=lambda p: p.name):
            if not acc_dir.is_dir():
                continue
            email, name = self._resolve_account(acc_dir.name)
            target = _AccountTarget(email=email, name=name, root=acc_dir)
            for folder_dir in sorted(acc_dir.iterdir(), key=lambda p: p.name):
                if not folder_dir.is_dir():
                    continue
                emls = sorted(folder_dir.glob("*.eml"), key=lambda p: p.name)
                if not emls:
                    continue
                target.folders.append((folder_dir.name, folder_dir))
                target.total_files += len(emls)
            if target.folders:
                targets.append(target)
        return targets

    # ---- 日期过滤 ----

    def _in_range(self, parsed_date: str, eml_path: Path) -> bool:
        """按邮件日期过滤；Date 头解析失败时用文件修改时间兜底"""
        dt = None
        if parsed_date:
            try:
                dt = datetime.strptime(parsed_date, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                dt = None
        if dt is None:
            try:
                dt = datetime.fromtimestamp(eml_path.stat().st_mtime)
            except Exception:
                return False
        return self.date_start <= dt.date() <= self.date_end

    # ---- 主流程 ----

    def run(self):
        result = AuditResult()
        matcher = KeywordMatcher(self.keywords, self.case_sensitive, self.synonyms,
                                 self.categories)

        # 导出目录：优先用指定的时间戳目录（与 全部邮件 同级），否则新建
        if self.export_dir:
            self.export_dir.mkdir(parents=True, exist_ok=True)
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            (self.output_dir / ts).mkdir(parents=True, exist_ok=True)

        if not self.source_dir.is_dir():
            self.finished_ok.emit(result)
            return

        self.log.emit(f"扫描本地目录: {self.source_dir}")
        targets = self._scan_targets()
        total = len(targets)
        total_files = sum(t.total_files for t in targets)
        if total == 0:
            self.log.emit("未找到任何 .eml 文件，请确认目录结构为 账号/文件夹/UID.eml")
            self.finished_ok.emit(result)
            return
        self.log.emit(f"共 {total} 个账号目录, {total_files} 封邮件待审计")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_map = {
                executor.submit(self._audit_one, t, matcher): t for t in targets
            }
            for i, fut in enumerate(as_completed(future_map), 1):
                if self.is_cancelled():
                    break
                t = future_map[fut]
                try:
                    acc_result = fut.result()
                    for r in acc_result["records"]:
                        result.add_record(r)
                    self.account_done.emit(t.email, len(acc_result["records"]))
                except Exception as e:
                    err_msg = f"{type(e).__name__}: {e}"
                    result.add_failure(t.email, err_msg)
                    self.account_failed.emit(t.email, err_msg)
                self.progress.emit(i, total, f"已完成 {i}/{total}")

        self.finished_ok.emit(result)

    def _audit_one(self, target: _AccountTarget,
                   matcher: KeywordMatcher) -> dict:
        """审计单个本地账号目录"""
        records: List[HitRecord] = []

        if self.is_cancelled():
            return {"records": records}

        self.account_started.emit(target.email)
        self.log.emit(f"[{target.email}] 扫描 {len(target.folders)} 个文件夹, "
                      f"共 {target.total_files} 封")

        for display, folder_dir in target.folders:
            if self.is_cancelled():
                break
            emls = sorted(folder_dir.glob("*.eml"), key=lambda p: p.name)
            folder_hits = 0
            folder_total = len(emls)
            folder_done = 0
            for eml_path in emls:
                if self.is_cancelled():
                    break
                folder_done += 1
                if folder_done % 10 == 0 or folder_done == folder_total:
                    self.log.emit(f"[{target.email}] {display}: "
                                  f"已处理 {folder_done}/{folder_total}")
                try:
                    raw = eml_path.read_bytes()
                    parsed = MailParser.parse(raw)
                    if not self._in_range(parsed.date, eml_path):
                        continue
                    hit_kws, hit_fields, hit_content, hit_synonym, hit_cats = matcher.match_record(parsed)
                    if hit_kws:
                        stem = eml_path.stem
                        uid = int(stem) if stem.isdigit() else 0
                        records.append(HitRecord(
                            account=target.email,
                            account_name=target.name,
                            folder=display,
                            uid=uid,
                            date=parsed.date,
                            from_=parsed.from_,
                            to=parsed.to,
                            cc=parsed.cc,
                            subject=parsed.subject,
                            hit_keywords=hit_kws,
                            hit_categories=hit_cats,
                            hit_fields=hit_fields,
                            hit_content=hit_content,
                            hit_synonym=hit_synonym,
                            eml_path=str(eml_path),   # 指向本地源文件，导出时再复制到 命中邮件
                        ))
                        folder_hits += 1
                except Exception as e:
                    self.log.emit(f"[{target.email}] {display} "
                                  f"{eml_path.name} 解析失败: {e}")

            self.folder_done.emit(target.email, display, folder_hits)

        return {"records": records}
