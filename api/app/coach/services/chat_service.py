"""S4 - Grounded chat assistant (FR-4.08)."""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.app.core.enums import MsgRole, RecStatus
from api.app.core.models import ChatMessage, ChatSession, Recommendation, User

from ..config import get_settings
from ..footprint import FootprintService, FootprintSummary
from ..llm import LLMClient, LLMError
from ..prompts import CHAT_SYSTEM
from ..schemas import ChatMessageOut, ChatReply
from .insight_service import rule_insights


def create_session(db: Session, user: User, title: str | None) -> ChatSession:
    s = ChatSession(user_id=user.id, title=(title or "New conversation")[:120])
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def list_sessions(db: Session, user: User) -> list[ChatSession]:
    return db.query(ChatSession).filter(ChatSession.user_id == user.id).order_by(ChatSession.created_at.desc()).all()


def get_session(db: Session, user: User, session_id: UUID) -> ChatSession:
    # Sessions are private to their owner (NFR-4.03)
    s = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == user.id).first()
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat session not found")
    return s


def get_messages(db: Session, session: ChatSession) -> list[ChatMessage]:
    return db.query(ChatMessage).filter(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at).all()


def delete_session(db: Session, user: User, session_id: UUID) -> None:
    s = get_session(db, user, session_id)
    db.query(ChatMessage).filter(ChatMessage.session_id == s.id).delete()
    db.delete(s)
    db.commit()


def _context(db: Session, user: User, summary: FootprintSummary) -> str:
    recs = (
        db.query(Recommendation)
        .filter(Recommendation.org_id == user.org_id,
                Recommendation.status.in_([RecStatus.proposed, RecStatus.accepted]))
        .order_by(Recommendation.est_saving_t_co2e.desc()).limit(8).all()
    )
    payload = {
        "footprint": summary.to_prompt_context(),
        "open_recommendations": [
            {"title": r.title, "status": r.status.value,
             "est_saving_t_co2e": float(r.est_saving_t_co2e or 0), "scope": r.scope.value if r.scope else None}
            for r in recs
        ],
        "user_role": user.role.value if user.role else None,
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def _fallback_answer(summary: FootprintSummary) -> str:
    lines = ["The AI assistant is not available right now. Here is a summary of your footprint instead:"]
    lines += [f"- {i}" for i in rule_insights(summary)]
    return "\n".join(lines)


def send_message(db: Session, user: User, llm: LLMClient | None, session_id: UUID, content: str) -> ChatReply:
    s = get_settings()
    content = content.strip()
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Message is empty")
    if len(content) > s.max_chat_message_chars:  # NFR-4.09
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Message is too long (max {s.max_chat_message_chars} characters)")

    session = get_session(db, user, session_id)
    history = get_messages(db, session)[-s.chat_history_window:]  # NFR-4.06 bounded context

    user_msg = ChatMessage(session_id=session.id, role=MsgRole.user, content=content)
    db.add(user_msg)
    if session.title in (None, "", "New conversation"):
        session.title = content[:60]
    db.commit()
    db.refresh(user_msg)

    summary = FootprintService(db).build(user.org_id)
    degraded = False
    tokens_in = tokens_out = 0
    if llm is None:
        answer, degraded = _fallback_answer(summary), True
    else:
        messages = [{"role": "system", "content": CHAT_SYSTEM.format(context=_context(db, user, summary))}]
        messages += [{"role": m.role.value, "content": m.content} for m in history]
        messages.append({"role": "user", "content": content})
        try:
            answer, usage = llm.chat(messages, s.max_tokens_chat)
            tokens_in, tokens_out = usage.tokens_in, usage.tokens_out
        except LLMError:
            answer, degraded = _fallback_answer(summary), True

    bot_msg = ChatMessage(session_id=session.id, role=MsgRole.assistant, content=answer,
                          tokens_in=tokens_in, tokens_out=tokens_out)
    db.add(bot_msg)
    db.commit()
    db.refresh(bot_msg)
    return ChatReply(
        session_id=session.id,
        user_message=ChatMessageOut.model_validate(user_msg),
        assistant_message=ChatMessageOut.model_validate(bot_msg),
        degraded=degraded,
    )
