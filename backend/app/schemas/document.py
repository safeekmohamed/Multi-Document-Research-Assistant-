from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    source_type: str
    source_url: str | None = None


class DocumentListItem(BaseModel):
    id: str
    filename: str
    file_type: str
    source_type: str
    source_url: str | None = None