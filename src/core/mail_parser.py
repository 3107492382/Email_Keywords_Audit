"""邮件解析器 — 从原始字节解析为结构化对象"""
import email
from dataclasses import dataclass, field
from email.policy import default as default_policy
from email.utils import parsedate_to_datetime
from typing import List


@dataclass
class ParsedMail:
    """解析后的邮件"""
    subject: str = ""
    from_: str = ""
    to: str = ""
    cc: str = ""
    date: str = ""
    body: str = ""
    attachments: List[str] = field(default_factory=list)


class MailParser:
    """将 RFC822 原始字节解析为 ParsedMail"""

    @staticmethod
    def parse(raw: bytes) -> ParsedMail:
        msg = email.message_from_bytes(raw, policy=default_policy)

        subject = str(msg.get("subject", "") or "")
        from_ = str(msg.get("from", "") or "")
        to = str(msg.get("to", "") or "")
        cc = str(msg.get("cc", "") or "")
        date_ = str(msg.get("date", "") or "")
        if date_:
            try:
                dt = parsedate_to_datetime(date_)
                date_ = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

        body = MailParser._extract_body(msg)
        attachments = MailParser._extract_attachments(msg)

        return ParsedMail(
            subject=subject,
            from_=from_,
            to=to,
            cc=cc,
            date=date_,
            body=body,
            attachments=attachments,
        )

    @staticmethod
    def _extract_body(msg) -> str:
        """提取正文：优先 text/plain，其次 text/html 转"""
        body_text = ""

        # 先找 text/plain
        for part in msg.walk():
            ct = part.get_content_type()
            disp = str(part.get("content_disposition", "") or "")
            if ct == "text/plain" and "attachment" not in disp.lower():
                try:
                    body_text = part.get_content()
                except Exception:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body_text = payload.decode(charset, errors="replace")
                break

        # 没有 text/plain，取 text/html 转纯文本
        if not body_text:
            for part in msg.walk():
                ct = part.get_content_type()
                disp = str(part.get("content_disposition", "") or "")
                if ct == "text/html" and "attachment" not in disp.lower():
                    try:
                        html = part.get_content()
                    except Exception:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            html = payload.decode(charset, errors="replace")
                        else:
                            html = ""
                    body_text = MailParser._html_to_text(html)
                    break

        # 限制正文长度避免超长邮件拖慢匹配
        if len(body_text) > 500_000:
            body_text = body_text[:500_000] + "\n[... 正文过长已截断 ...]"
        return body_text

    @staticmethod
    def _html_to_text(html: str) -> str:
        """HTML 转纯文本，用标准库 html.parser 避免引入 lxml"""
        try:
            from bs4 import BeautifulSoup
            return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        except ImportError:
            # 降级：简单去除标签
            import re
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            return text

    @staticmethod
    def _extract_attachments(msg) -> List[str]:
        """提取附件文件名列表"""
        names = []
        for part in msg.walk():
            disp = str(part.get("content_disposition", "") or "")
            if "attachment" in disp.lower():
                fname = part.get_filename()
                if fname:
                    # 解码 RFC2047 文件名
                    from email.header import decode_header
                    try:
                        decoded = decode_header(fname)
                        fname = "".join(
                            s if isinstance(s, str) else s.decode(enc or "utf-8", errors="replace")
                            for s, enc in decoded
                        )
                    except Exception:
                        pass
                    names.append(fname)
        return names
