from typing import Literal

from pydantic import BaseModel, Field, field_validator


FeedbackCategory = Literal["bug_report", "suggestion", "general"]


class FeedbackCreateRequest(BaseModel):
    category: FeedbackCategory
    message: str = Field(min_length=1, max_length=5000)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        message = value.strip()
        if not message:
            raise ValueError("Feedback message cannot be empty.")
        if any(ord(character) < 32 and character not in "\n\r\t" for character in message):
            raise ValueError("Feedback message contains unsupported control characters.")
        return message
