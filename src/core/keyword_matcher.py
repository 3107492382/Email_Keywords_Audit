"""关键词匹配器 — 在邮件各字段中搜索关键词（substring 匹配，中英通用），支持同义词库扩展"""
from typing import Dict, List, Set, Tuple

from src.core.mail_parser import ParsedMail


class KeywordMatcher:
    """substring 匹配，支持同义词扩展"""

    FIELDS = ("subject", "from", "to", "cc", "body", "attachment")

    def __init__(self, keywords: List[str], case_sensitive: bool = False,
                 synonyms: Dict[str, list] = None,
                 categories: Dict[str, str] = None):
        self.case_sensitive = case_sensitive
        self._synonyms = synonyms or {}
        self._categories = categories or {}

        # 主词去重去空
        seen = set()
        self.keywords = []
        for k in keywords:
            k = (k or "").strip()
            if k and k not in seen:
                seen.add(k)
                self.keywords.append(k)

        # 每个主词展开为 [主词本身] + 同义词列表
        self._expanded: Dict[str, List[str]] = {}
        for kw in self.keywords:
            words = [kw] + self._synonyms.get(kw, [])
            # 同义词也去重
            deduped = []
            for w in words:
                w = w.strip()
                if w and w not in deduped:
                    deduped.append(w)
            self._expanded[kw] = deduped

        # 预处理：小写版本用于快速包含检查
        self._lower_expanded = (
            {kw: [w.lower() for w in words] for kw, words in self._expanded.items()}
            if not case_sensitive else self._expanded
        )

    def match(self, text: str) -> Dict[str, str]:
        """在单个文本中匹配，返回 {主词: 实际命中的词}（实际命中词可能是主词或同义词）"""
        if not text:
            return {}
        hits = {}
        search_text = text if self.case_sensitive else text.lower()
        for kw in self.keywords:
            for i, lkw in enumerate(self._lower_expanded[kw]):
                if lkw in search_text:
                    actual = self._expanded[kw][i]  # 原始词（未小写化）
                    hits[kw] = actual
                    break
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
        """提取关键词所在的完整句子（按句号/换行/问号/感叹号分割）。
        keyword 是主词，会尝试主词和同义词找到最先命中的位置。"""
        if not text or not keyword:
            return text[:max_len] if text else ""
        search_text = text if self.case_sensitive else text.lower()
        # 尝试主词和所有同义词，取最先命中的位置
        words = self._expanded.get(keyword, [keyword])
        pos = -1
        hit_word = keyword
        for w in words:
            lw = w if self.case_sensitive else w.lower()
            p = search_text.find(lw)
            if p >= 0 and (pos < 0 or p < pos):
                pos = p
                hit_word = w
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
        end = pos + len(hit_word)
        for i in range(end, len(text)):
            if text[i] in delimiters:
                end = i + 1
                break
        else:
            end = len(text)

        sentence = text[start:end].strip()
        if len(sentence) > max_len:
            lw = hit_word if self.case_sensitive else hit_word.lower()
            kw_pos = sentence.lower().find(lw) if not self.case_sensitive else sentence.find(hit_word)
            s = max(0, kw_pos - 100)
            e = min(len(sentence), kw_pos + len(hit_word) + 200)
            sentence = sentence[s:e]
            if s > 0:
                sentence = "..." + sentence
            if e < len(text[start:end].strip()):
                sentence = sentence + "..."
        return sentence

    def match_record(self, parsed: ParsedMail) -> Tuple[List[str], List[str], str, List[str], List[str]]:
        """在邮件所有字段中匹配，返回
        (命中关键词列表, 命中字段列表, 命中内容, 命中同义词列表, 命中类别列表)。
        命中同义词：如果命中的是同义词而非主词本身，列出实际命中的同义词。
        主词直接命中则该列表为空。命中类别与命中关键词一一对应（无类别为空字符串）。"""
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
        hit_synonyms = set()  # 实际命中且不等于主词的词
        for fname in self.FIELDS:
            text = fields_text.get(fname, "")
            hits = self.match(text)
            if hits:
                all_hits.update(hits.keys())
                for kw, actual in hits.items():
                    if actual != kw:
                        hit_synonyms.add(actual)
                hit_fields.append(fname)
                label = self.FIELD_LABELS.get(fname, fname)
                if fname == "body":
                    # 正文提取每个命中关键词的上下文
                    snippets = []
                    for kw in sorted(hits.keys()):
                        snippets.append(self._extract_sentence(text, kw))
                    content = " | ".join(snippets)
                    if len(content) > 500:
                        content = content[:500] + "..."
                    hit_content_parts.append(f"[{label}] {content}")
                else:
                    hit_content_parts.append(f"[{label}] {text}")
        hit_kws = sorted(all_hits)
        hit_categories = [self._categories.get(kw, "") for kw in hit_kws]
        return hit_kws, hit_fields, "\n".join(hit_content_parts), sorted(hit_synonyms), hit_categories
