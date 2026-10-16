from pydantic import BaseModel


class AdminUserResponse(BaseModel):

    id: str
    name: str
    email: str
    is_verified: bool
    is_blocked: bool
    role: str
    created_at: str | None = None


class AdminActionResponse(BaseModel):

    message: str
    user: AdminUserResponse