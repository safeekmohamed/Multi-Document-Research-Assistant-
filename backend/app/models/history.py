from dataclasses import dataclass
from datetime import datetime


@dataclass
class Conversation:
    user_id: str
    title: str
    created_at: datetime


@dataclass
class Message:
    conversation_id: str
    role: str
    content: str
    created_at: datetime