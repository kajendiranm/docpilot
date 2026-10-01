from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.llm import ChatMessage


class MessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    messages: list[MessageIn] = Field(min_length=1, max_length=50)

    @field_validator("messages")
    @classmethod
    def last_message_is_from_user(cls, messages: list[MessageIn]) -> list[MessageIn]:
        if messages[-1].role != "user":
            raise ValueError("the last message must be from the user")
        return messages

    def to_chat_messages(self) -> list[ChatMessage]:
        return [ChatMessage(role=m.role, content=m.content) for m in self.messages]


class IngestResponse(BaseModel):
    files_seen: int
    processed: int
    skipped: int
    removed: int
    chunks_created: int
    seconds: float


class DocumentInfo(BaseModel):
    path: str
    title: str | None
    chunks: int
    ingested_at: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, str]  # component -> "ok" or an error message
