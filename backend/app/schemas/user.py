from pydantic import BaseModel, EmailStr


class UserResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    is_verified: bool