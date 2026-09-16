"""关键词匹配器 — 在邮件各字段中搜索关键词（substring 匹配，中英通用）"""
from typing import List, Set, Tuple, Dict

from src.core.mail_parser import ParsedMail


class KeywordMatcher:
    """统一 substring 匹配，中文英文都能命中"""

    FIELDS = ("subject", "from", "to", "cc", "body", "attachment")

    def __init__(self, keywords: List[str], case_sensitive: bool = False):
        self.case_sensitive = case_sensitive
        # 去重、去空、去首尾空格
        seen = set()
        self.keywords = []
        for k in keywords:
            k = (k or "").strip()
            if k and k not in seen:
                seen.add(k)
                self.keywords.append(k)
        # 预处理：小写版本用于快速包含检查
        self._lower_keywords = (
            [k.lower() for k in self.keywords] if not case_sensitive else self.keywords
        )

    def match(self, text: str) -> Set[str]:
        """在单个文本中匹配，返回命中关键词集合"""
        if not text:
            return set()
        hits = set()
        search_text = text if self.case_sensitive else text.lower()
        for kw, lkw in zip(self.keywords, self._lower_keywords):
            if lkw in search_text:
                hits.add(kw)
        return hits

    # 字段中文显示名
    FIELD_LABELS = {
        "subject": "主题",
        "from": "发件人",
        "to": "收件人",
        "cc": "抄送",
        "body": "正文",
        "attachment": "附件",
    }

    def _extract_sentence(self, text: str, keyword: str, max_len: int = 500) -> str:
        """提取关键词所在的完整句子（按句号/换行/问号/感叹号分割）"""
        if not text or not keyword:
            return text[:max_len] if text else ""
        search_text = text if self.case_sensitive else text.lower()
        kw = keyword if self.case_sensitive else keyword.lower()
        pos = search_text.find(kw)
        if pos < 0:
            return text[:max_len]

        # 句子分隔符：中英文句号、问号、感叹号、换行
        delimiters = "。！？!?\n\r"
        # 向前找句子起点
        start = pos
        for i in range(pos - 1, -1, -1):
            if text[i] in delimiters:
                start = i + 1
                break
        # 向后找句子终点
        end = pos + len(keyword)
        for i in range(end, len(text)):
            if text[i] in delimiters:
                end = i + 1
                break
        else:
            end = len(text)

        sentence = text[start:end].strip()
        if len(sentence) > max_len:
            # 句子太长，以关键词为中心截取
            kw_pos = sentence.lower().find(kw) if not self.case_sensitive else sentence.find(kw)
            s = max(0, kw_pos - 100)
            e = min(len(sentence), kw_pos + len(keyword) + 200)
            sentence = sentence[s:e]
            if s > 0:
                sentence = "..." + sentence
            if e < len(text[start:end].strip()):
                sentence = sentence + "..."
        return sentence

    def match_record(self, parsed: ParsedMail) -> Tuple[List[str], List[str], str]:
        """在邮件所有字段中匹配，返回 (命中关键词列表, 命中字段列表, 命中内容)"""
        fields_text = {
            "subject": parsed.subject or "",
            "from": parsed.from_ or "",
            "to": parsed.to or "",
            "cc": parsed.cc or "",
            "body": parsed.body or "",
            "attachment": " ".join(parsed.attachments),
        }
        all_hits = set()
        hit_fields = []
        hit_content_parts = []
        for fname in self.FIELDS:
            text = fields_text.get(fname, "")
            hits = self.match(text)
            if hits:
                all_hits.update(hits)
                hit_fields.append(fname)
                label = self.FIELD_LABELS.get(fname, fname)
                if fname == "body":
                    # 正文提取每个命中关键词的上下文
                    snippets = []
                    for kw in sorted(hits):
                        snippets.append(self._extract_sentence(text, kw))
                    content = " | ".join(snippets)
                    if len(content) > 500:
                        content = content[:500] + "..."
                    hit_content_parts.append(f"[{label}] {content}")
                else:
                    hit_content_parts.append(f"[{label}] {text}")
        return sorted(all_hits), hit_fields, "\n".join(hit_content_parts)
