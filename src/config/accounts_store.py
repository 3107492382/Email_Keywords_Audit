"""账号存储 — 加密文件读写（无需主密码）"""
import os
from pathlib import Path
from typing import List, Optional

from src.config.crypto import AccountsCrypto, CryptoError
from src.models.account import Account


class AccountsStore:
    """管理加密的账号文件 accounts.enc"""

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
            base_dir = Path(appdata) / "email_audit"
        base_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = base_dir / "accounts.enc"

    def exists(self) -> bool:
        return self.file_path.exists()

    def initialize(self) -> None:
        """首次创建空账号文件"""
        self.save([])

    def save(self, accounts: List[Account]) -> None:
        data = [a.to_dict() for a in accounts]
        token = AccountsCrypto.encrypt(data)
        self.file_path.write_bytes(token)

    def load(self) -> List[Account]:
        if not self.exists():
            return []
        token = self.file_path.read_bytes()
        data_list = AccountsCrypto.decrypt(token)
        return [Account.from_dict(d) for d in data_list]
