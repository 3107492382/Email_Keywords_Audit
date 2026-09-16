"""EML 原文导出器"""
import re
from pathlib import Path


class EmlExporter:
    """将邮件原始字节保存为 .eml 文件"""

    @staticmethod
    def save(raw: bytes, account: str, folder: str, uid: int,
             base_dir: Path, account_name: str = "") -> Path:
        # 优先用姓名做目录名，没填则 fallback 到邮箱
        dir_name = account_name.strip() if account_name else account
        safe_account = EmlExporter._sanitize(dir_name)
        safe_folder = EmlExporter._sanitize(folder)
        out_dir = base_dir / safe_account / safe_folder
        out_dir.mkdir(parents=True, exist_ok=True)
        file_path = out_dir / f"{uid}.eml"
        file_path.write_bytes(raw)
        return file_path

    @staticmethod
    def _sanitize(name: str) -> str:
        """清理路径中的非法字符"""
        return re.sub(r'[\\/:*?"<>|]', "_", name)
