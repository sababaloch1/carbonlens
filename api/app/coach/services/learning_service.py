"""S4 - Educational content with an approval workflow (FR-4.09, FR-4.10).

Content is generated from a topic and audience only; no company data is sent
to the model (NFR-4.02). New content starts as a draft and contributors only
see approved articles.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.app.core.enums import ContentStatus, UserRole
from api.app.core.models import LearningContent, User

from ..config import get_settings
from ..llm import LLMClient, LLMError
from ..prompts import LEARNING_SYSTEM


def generate(db: Session, llm: LLMClient | None, topic: str, audience: UserRole) -> LearningContent:
    if llm is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI is not configured (OPENAI_API_KEY missing)")
    user_prompt = f"Audience role: {audience.value}\nTopic: {topic.strip()}"
    try:
        data, _ = llm.complete_json(LEARNING_SYSTEM, user_prompt, get_settings().max_tokens_learning)
    except LLMError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"AI unavailable: {exc}")
    body = str(data.get("body", "")).strip()
    if len(body) < 50:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "AI returned unusable content, please retry")
    title = str(data.get("title") or topic).strip()[:160]
    item = LearningContent(topic=title, audience=audience, body=body, status=ContentStatus.draft)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_content(db: Session, user: User, audience: UserRole | None = None,
                 status_filter: ContentStatus | None = None) -> list[LearningContent]:
    q = db.query(LearningContent)
    if user.role == UserRole.contributor:
        q = q.filter(LearningContent.status == ContentStatus.approved)  # drafts hidden
    elif status_filter:
        q = q.filter(LearningContent.status == status_filter)
    if audience:
        q = q.filter(LearningContent.audience == audience)
    return q.order_by(LearningContent.created_at.desc()).all()


def get_content(db: Session, user: User, content_id: UUID) -> LearningContent:
    item = db.query(LearningContent).filter(LearningContent.id == content_id).first()
    if not item or (user.role == UserRole.contributor and item.status != ContentStatus.approved):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")
    return item


def approve(db: Session, content_id: UUID) -> LearningContent:
    item = db.query(LearningContent).filter(LearningContent.id == content_id).first()
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")
    item.status = ContentStatus.approved
    db.commit()
    db.refresh(item)
    return item


def delete(db: Session, content_id: UUID) -> None:
    item = db.query(LearningContent).filter(LearningContent.id == content_id).first()
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")
    db.delete(item)
    db.commit()
