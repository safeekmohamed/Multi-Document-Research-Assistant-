from pydantic import BaseModel


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: str


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str