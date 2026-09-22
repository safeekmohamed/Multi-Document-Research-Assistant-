from dataclasses import dataclass
from datetime import datetime


@dataclass
class Document:
    user_id: str
    filename: str
    file_type: str
    source_type: str
    source_url: str | None = None
    created_at: datetime | None = None