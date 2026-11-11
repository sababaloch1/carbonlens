"""S4 - Pydantic schemas (API contracts + validation of model output)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.app.core.enums import (
    ActivityCategory, ContentStatus, Level, MsgRole, RecSource, RecStatus, Scope, UserRole,
)


class GenerationMode(str, Enum):
    auto = "auto"    # try OpenAI, fall back to rules
    ai = "ai"        # OpenAI only (503 if unavailable)
    rules = "rules"  # deterministic rules only


# ---------------- Recommendations ----------------
class RecommendationOut(BaseModel):
    id: UUID
    org_id: UUID
    department_id: Optional[UUID] = None
    title: str
    description: Optional[str] = None
    est_saving_t_co2e: Optional[float] = None
    cost_level: Optional[Level] = None
    effort: Optional[Level] = None
    scope: Optional[Scope] = None
    status: RecStatus
    source: Optional[RecSource] = None
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class GenerateRequest(BaseModel):
    mode: GenerationMode = GenerationMode.auto


class GenerateResponse(BaseModel):
    source_used: Optional[RecSource] = None
    created: list[RecommendationOut]
    skipped_duplicates: int = 0
    warning: Optional[str] = None


class StatusUpdate(BaseModel):
    status: RecStatus


class AIRecommendationItem(BaseModel):
    """Validates one recommendation returned by the model (NFR-4.05)."""
    title: str = Field(..., min_length=5, max_length=160)
    description: str = Field(..., min_length=10, max_length=2000)
    reasoning: str = Field("", max_length=1000)
    category: Optional[ActivityCategory] = None
    est_saving_t_co2e: float = Field(..., ge=0)
    cost_level: Level
    effort: Level
    scope: Scope
    department: Optional[str] = None

    @field_validator("title", "description", "reasoning", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("category", mode="before")
    @classmethod
    def _unknown_category_to_none(cls, v):
        try:
            return ActivityCategory(v) if v else None
        except ValueError:
            return None


# ---------------- Insights ----------------
class InsightsResponse(BaseModel):
    source: RecSource
    insights: list[str]
    summary: dict
    warning: Optional[str] = None


# ---------------- Chat ----------------
class ChatSessionCreate(BaseModel):
    title: Optional[str] = Field(None, max_length=120)


class ChatSessionOut(BaseModel):
    id: UUID
    title: Optional[str] = None
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class ChatMessageIn(BaseModel):
    content: str = Field(..., min_length=1)


class ChatMessageOut(BaseModel):
    id: UUID
    role: MsgRole
    content: str
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class ChatReply(BaseModel):
    session_id: UUID
    user_message: ChatMessageOut
    assistant_message: ChatMessageOut
    degraded: bool = False


# ---------------- Learning content ----------------
class LearningGenerate(BaseModel):
    topic: str = Field(..., min_length=3, max_length=160)
    audience: UserRole = UserRole.contributor


class LearningOut(BaseModel):
    id: UUID
    topic: Optional[str] = None
    audience: Optional[UserRole] = None
    body: Optional[str] = None
    status: ContentStatus
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# ---------------- Usage ----------------
class CoachUsage(BaseModel):
    model: str
    ai_enabled: bool
    chat_sessions: int
    chat_messages: int
    tokens_in: int
    tokens_out: int
    recommendations_by_source: dict[str, int]
    recommendations_by_status: dict[str, int]


# ---------------- What-if (FR-4.07) ----------------
class WhatIfRequest(BaseModel):
    scenario_id: str
    change_pct: float = Field(50, gt=0, le=100, description="Share of the activity that is cut or replaced (%)")
    save: bool = Field(False, description="Save the result as a recommendation (manager/admin)")


class WhatIfResult(BaseModel):
    scenario_id: str
    title: str
    change_pct: float
    year: Optional[int] = None
    before_t_co2e: float
    after_t_co2e: float
    saving_t_co2e: float
    saving_pct: Optional[float] = None
    saving_cost_eur: Optional[float] = Field(None, description="None when the engine has no tariff for some items")
    assumptions: str
    engine_errors: int = 0


class WhatIfResponse(BaseModel):
    result: WhatIfResult
    saved_recommendation: Optional[RecommendationOut] = None
