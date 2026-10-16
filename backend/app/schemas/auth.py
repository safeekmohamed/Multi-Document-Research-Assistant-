from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp_code: str = Field(min_length=6, max_length=6)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ResendOTPRequest(BaseModel):
    email: EmailStr


class PasswordSetupRequest(BaseModel):
    email: EmailStr


class PasswordSetupConfirmRequest(BaseModel):
    email: EmailStr
    otp_code: str = Field(pattern=r"^\d{6}$")
    password: str = Field(min_length=6, max_length=128)


class GooglePasswordSetupRequest(BaseModel):
    setup_code: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=6, max_length=128)