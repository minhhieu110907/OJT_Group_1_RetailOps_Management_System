"""Strict Pydantic DTOs for the RetailOps AI Assistant endpoint."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

AI_QUERY_MAX_LENGTH = 4000


class _AIStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AIQueryRequest(_AIStrictModel):
    """Request payload for POST /api/v1/ai/query (never accepts user_id or role)."""

    message: str = Field(min_length=1, max_length=AI_QUERY_MAX_LENGTH)

    @field_validator("message")
    @classmethod
    def validate_non_blank_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Câu hỏi không được để trống.")
        return cleaned


class AIEvidence(_AIStrictModel):
    """Evidence item matching frontend AIEvidence contract (3 fields only)."""

    source: str = Field(min_length=1)
    period: str | None
    summary: str = Field(min_length=1)


class AIAskResponse(_AIStrictModel):
    """Response payload matching frontend AIAskResponse contract."""

    answer: str = Field(min_length=1)
    evidence: list[AIEvidence]
    insufficient_data: bool
