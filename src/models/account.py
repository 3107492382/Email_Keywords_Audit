"""账号数据模型"""
from dataclasses import dataclass


@dataclass
class Account:
    """单个邮箱账号"""
    email: str
    auth_code: str
    name: str = ""

    def __post_init__(self):
        self.email = (self.email or "").strip()
        self.auth_code = (self.auth_code or "").strip()
        self.name = (self.name or "").strip()

    def to_dict(self) -> dict:
        return {"email": self.email, "auth_code": self.auth_code, "name": self.name}

    @classmethod
    def from_dict(cls, d: dict) -> "Account":
        return cls(email=d.get("email", ""), auth_code=d.get("auth_code", ""), name=d.get("name", ""))
