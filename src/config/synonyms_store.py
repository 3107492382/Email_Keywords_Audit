"""同义词库读写 — synonyms.json"""
import json
import os
from pathlib import Path
from typing import Dict, Optional


class SynonymsStore:
    """同义词库持久化，格式: {"主词": ["同义词1", "同义词2"], ...}"""

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
            base_dir = Path(appdata) / "email_audit"
        base_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = base_dir / "synonyms.json"

    def load(self) -> Dict[str, list]:
        """加载同义词库，文件不存在时返回空 dict"""
        if not self.file_path.exists():
            return {}
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
            # 确保格式正确：每个值都是 list[str]
            result = {}
            for k, v in data.items():
                if isinstance(v, list):
                    result[k] = [s for s in v if isinstance(s, str) and s.strip()]
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    def save(self, synonyms: Dict[str, list]) -> None:
        """保存同义词库"""
        # 清理空值和空列表
        cleaned = {}
        for k, v in synonyms.items():
            k = (k or "").strip()
            if not k:
                continue
            words = [s.strip() for s in v if isinstance(s, str) and s.strip()]
            # 主词自身不重复出现在同义词列表里
            words = [w for w in words if w != k]
            if words:
                cleaned[k] = words
        self.file_path.write_text(
            json.dumps(cleaned, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
