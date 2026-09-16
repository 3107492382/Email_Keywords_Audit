"""配置加密 — 基于机器特征派生密钥（用户无感知）"""
import base64
import json
import os
import platform
import socket
import uuid
from typing import List

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class CryptoError(Exception):
    pass


class AccountsCrypto:
    """基于机器特征自动派生密钥的加解密"""

    _SALT = b"email_audit_machine_salt_v1"
    _VERIFY = "AUDIT_VERIFY_TOKEN_v1"
    _ITERATIONS = 100_000

    @classmethod
    def _machine_fingerprint(cls) -> str:
        """收集本机特征生成稳定指纹"""
        parts = []
        try:
            parts.append(str(uuid.getnode()))            # MAC 地址
        except Exception:
            pass
        parts.append(platform.node() or "")              # 计算机名
        parts.append(platform.processor() or "")
        try:
            parts.append(os.environ.get("COMPUTERNAME", ""))
        except Exception:
            pass
        try:
            parts.append(os.environ.get("USERNAME", ""))
        except Exception:
            pass
        return "|".join(parts)

    @classmethod
    def derive_key(cls) -> bytes:
        """从机器特征派生 Fernet 密钥"""
        secret = cls._machine_fingerprint().encode("utf-8")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=cls._SALT,
            iterations=cls._ITERATIONS,
        )
        return base64.urlsafe_b64encode(kdf.derive(secret))

    @classmethod
    def encrypt(cls, accounts_data: List[dict]) -> bytes:
        key = cls.derive_key()
        f = Fernet(key)
        payload = {"verify": cls._VERIFY, "accounts": accounts_data}
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return f.encrypt(raw)

    @classmethod
    def decrypt(cls, token: bytes) -> List[dict]:
        key = cls.derive_key()
        f = Fernet(key)
        try:
            raw = f.decrypt(token)
        except InvalidToken:
            raise CryptoError("解密失败：可能数据已损坏或机器特征已改变")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise CryptoError("数据格式损坏")
        if data.get("verify") != cls._VERIFY:
            raise CryptoError("数据校验失败")
        return data.get("accounts", [])
