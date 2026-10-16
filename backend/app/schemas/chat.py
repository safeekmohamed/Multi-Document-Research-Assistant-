from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    conversation_id: str | None = None
    attachment_document_ids: list[str] = Field(
        default_factory=list,
        max_length=10,
    )
