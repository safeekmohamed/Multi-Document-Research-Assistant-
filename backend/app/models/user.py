from dataclasses import dataclass
from datetime import datetime


@dataclass
class User:
    name: str
    email: str
    password_hash: str
    is_verified: bool = False
    created_at: datetime | None = None