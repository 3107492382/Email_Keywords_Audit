"""IMAP 客户端封装 — 只读访问腾讯企业邮箱"""
import base64
import imaplib
import re
from datetime import date, timedelta
from typing import Iterator, List, Optional, Tuple


def decode_imap_utf7(name: str) -> str:
    """将 IMAP modified UTF-7 (RFC 3501) 解码为 UTF-8

    IMAP modified UTF-7 规则:
      - 直接 ASCII 原样保留
      - 非 ASCII 用 "&" 开头、"-" 结尾
      - "&" 本身编码为 "&-"
      - 中间的 base64 使用 "," 代替 "/"
      - base64 内容为 UTF-16-BE 编码
    """
    if "&" not in name:
        return name

    def _decode_chunk(match: re.Match) -> str:
        body = match.group(1)  # & 和 - 之间的内容
        if not body:
            # "&-" 表示字面量 "&"
            return "&"
        # IMAP UTF-7: 用 "," 代替 "/"
        body = body.replace(",", "/")
        # base64 padding
        padding = (-len(body)) % 4
        body += "=" * padding
        try:
            raw = base64.b64decode(body)
            return raw.decode("utf-16-be")
        except Exception:
            return match.group(0)

    return re.sub(r"&([^-]*)-", _decode_chunk, name)


class ImapError(Exception):
    pass


class FolderNotFoundError(ImapError):
    pass


class ImapClient:
    """对 imaplib 的轻量封装，确保只读审计"""

    def __init__(self, host: str = "imap.exmail.qq.com", port: int = 993,
                 use_ssl: bool = True, timeout: int = 30):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.timeout = timeout
        self._conn: Optional[imaplib.IMAP4] = None

    # ---- 连接管理 ----

    def connect(self, email_addr: str, auth_code: str) -> None:
        try:
            if self.use_ssl:
                self._conn = imaplib.IMAP4_SSL(self.host, self.port, timeout=self.timeout)
            else:
                self._conn = imaplib.IMAP4(self.host, self.port, timeout=self.timeout)
            typ, data = self._conn.login(email_addr, auth_code)
            if typ != "OK":
                raise ImapError(f"登录失败: {data}")
        except imaplib.IMAP4.error as e:
            raise ImapError(f"IMAP 登录失败: {e}")
        except OSError as e:
            raise ImapError(f"连接服务器失败: {e}")

    def logout(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            try:
                self._conn.logout()
            except Exception:
                pass
            self._conn = None

    # ---- 文件夹操作 ----

    def list_folders(self) -> List[dict]:
        """返回服务器上所有文件夹信息列表

        每个元素是 dict: {"raw": IMAP原始名, "name": 解码后的显示名, "flags": flag字符串}
        优先使用 name 做显示，raw 用于实际 IMAP 操作
        """
        if not self._conn:
            raise ImapError("未连接")
        typ, data = self._conn.list()
        folders: List[dict] = []
        if typ == "OK":
            for item in data:
                # IMAP LIST 响应格式: b'(\\HasNoChildren \\UnMarked) "/" "INBOX"'
                raw_line = item.decode("utf-8", errors="replace") if isinstance(item, bytes) else str(item)

                # 1. 提取 flags 部分: (...)
                flags = ""
                if raw_line.startswith("("):
                    end = raw_line.find(")")
                    if end > 0:
                        flags = raw_line[1:end]
                        rest = raw_line[end + 1:].lstrip()
                    else:
                        rest = raw_line
                else:
                    rest = raw_line

                # 2. rest 现在类似: "/" "INBOX" 或: "/" "&UXZO1mWHTvZZOQ-"
                #    separator 是带引号的，后面是带引号的文件夹名
                folder_raw = ""
                if '"' in rest:
                    # 找到最后一对引号中的内容 = 文件夹名
                    # rest 结构: <separator> "<name>"  或  "<separator>" "<name>"
                    # 取所有引号对里最后一个 = 文件夹名
                    parts = rest.split('"')
                    # parts: ['', '/', ' ', 'INBOX', ''] -> 倒数第二个是文件夹名
                    # parts: ['', '/', ' ', '&UXZO1mWHTvZZOQ-', ''] -> 倒数第二个是原始名
                    folder_raw = parts[-2] if len(parts) >= 2 else rest.strip()
                else:
                    folder_raw = rest.strip().split()[-1] if rest.strip() else ""

                folder_name = decode_imap_utf7(folder_raw)

                folders.append({
                    "raw": folder_raw,
                    "name": folder_name,
                    "flags": flags,
                })
        return folders

    def select_folder(self, folder: str) -> int:
        """选中文件夹（只读），返回邮件总数"""
        if not self._conn:
            raise ImapError("未连接")
        try:
            # 文件夹名可能含空格（如 "Sent Messages"）或 UTF-7 编码，必须加引号
            typ, data = self._conn.select(f'"{folder}"', readonly=True)
            if typ != "OK":
                raise FolderNotFoundError(f"文件夹 {folder} 不存在或不可访问")
            return int(data[0]) if data and data[0] else 0
        except imaplib.IMAP4.error as e:
            raise FolderNotFoundError(f"文件夹 {folder} 选择失败: {e}")

    # ---- 搜索与获取 ----

    # IMAP 协议要求英文月份缩写，不能依赖系统 locale
    _MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    @classmethod
    def _imap_date(cls, d: date) -> str:
        """格式化为 IMAP 要求的日期: 14-Sep-2026"""
        return f"{d.day:02d}-{cls._MONTH_ABBR[d.month - 1]}-{d.year}"

    def search_uids(self, folder: str, since: date, before: date) -> List[int]:
        """在指定文件夹内按时间范围搜索，返回 UID 列表"""
        self.select_folder(folder)
        # IMAP BEFORE 不含当天，所以 before 要 +1 天
        before_next = before + timedelta(days=1)
        since_str = self._imap_date(since)
        before_str = self._imap_date(before_next)
        typ, data = self._conn.uid("search", None, "SINCE", since_str, "BEFORE", before_str)
        if typ != "OK":
            return []
        uids = []
        if data and data[0]:
            for uid in data[0].split():
                try:
                    uids.append(int(uid))
                except ValueError:
                    pass
        return uids

    def fetch_batch(self, uids: List[int]) -> Iterator[Tuple[int, bytes]]:
        """批量获取邮件原文（BODY.PEEK[] 不标记已读）"""
        if not self._conn:
            raise ImapError("未连接")
        for uid in uids:
            try:
                typ, data = self._conn.uid("fetch", str(uid), "(BODY.PEEK[])")
                if typ != "OK":
                    continue
                raw = self._extract_raw(data)
                if raw:
                    yield uid, raw
            except imaplib.IMAP4.error:
                continue

    def _extract_raw(self, data) -> bytes:
        """从 fetch 响应中提取邮件原文"""
        for item in data:
            if isinstance(item, tuple):
                # 格式: (b'1 (BODY[]<n>)', b'邮件原文...')
                if len(item) >= 2:
                    return item[1]
        return b""

    # ---- 上下文管理 ----

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logout()
