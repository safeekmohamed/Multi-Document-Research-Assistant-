from dataclasses import dataclass
from datetime import datetime


@dataclass
class OTP:
    email: str
    otp_hash: str
    purpose: str
    expires_at: datetime
    is_used: bool = False