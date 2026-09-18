"""同义词库读写 — synonyms.json

新格式（含类别）:
{"主词": {"synonyms": ["同义词1", "同义词2"], "category": "财务相关"}, ...}
旧格式（兼容读取）:
{"主词": ["同义词1", "同义词2"], ...}
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional


class SynonymsStore:
    """同义词库持久化"""

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
            base_dir = Path(appdata) / "email_audit"
        base_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = base_dir / "synonyms.json"

    def load_full(self) -> Dict[str, dict]:
        """加载完整结构: {主词: {"synonyms": [...], "category": "..."}}"""
        if not self.file_path.exists():
            return {}
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, TypeError):
            return {}
        result: Dict[str, dict] = {}
        if not isinstance(data, dict):
            return {}
        for k, v in data.items():
            k = str(k).strip()
            if not k:
                continue
            if isinstance(v, list):
                # 旧格式
                words = [s.strip() for s in v if isinstance(s, str) and s.strip()]
                result[k] = {"synonyms": words, "category": ""}
            elif isinstance(v, dict):
                words = v.get("synonyms", [])
                words = [s.strip() for s in words if isinstance(s, str) and s.strip()]
                category = str(v.get("category", "") or "").strip()
                result[k] = {"synonyms": words, "category": category}
        return result

    def load(self) -> Dict[str, list]:
        """加载同义词库（旧签名），仅返回 {主词: [同义词...]}"""
        return {k: v["synonyms"] for k, v in self.load_full().items()}

    def save_full(self, full: Dict[str, dict]) -> None:
        """保存完整结构；空同义词且空类别的主词不保留"""
        cleaned: Dict[str, dict] = {}
        for k, v in full.items():
            k = (k or "").strip()
            if not k or not isinstance(v, dict):
                continue
            words = [s.strip() for s in v.get("synonyms", [])
                     if isinstance(s, str) and s.strip()]
            words = [w for w in words if w != k]  # 主词自身不进同义词列表
            category = (v.get("category", "") or "").strip()
            if not words and not category:
                continue
            cleaned[k] = {"synonyms": words, "category": category}
        self.file_path.write_text(
            json.dumps(cleaned, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save(self, synonyms: Dict[str, list]) -> None:
        """保存同义词库（旧签名），类别信息留空"""
        full = {k: {"synonyms": v, "category": ""} for k, v in synonyms.items()}
        self.save_full(full)
