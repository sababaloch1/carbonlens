from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.app.core.database import get_db
from api.app.core.deps import get_current_user
from api.app.core.models import ChatMessage, ChatSession, Recommendation, User

from ..config import get_settings
from ..footprint import FootprintService
from ..llm import LLMClient, get_llm
from ..schemas import CoachUsage, InsightsResponse
from ..services import insight_service

router = APIRouter(prefix="/coach", tags=["S4 Coach - Insights"])


# FR-4.01: aggregated footprint context used by the coach
@router.get("/summary")
def footprint_summary(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return FootprintService(db).build(current_user.org_id, date_from, date_to).to_dict()


# FR-4.02: AI explanation of what drives the footprint
@router.get("/insights", response_model=InsightsResponse)
def insights(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    llm: Optional[LLMClient] = Depends(get_llm),
):
    return insight_service.get_insights(db, current_user, llm, date_from, date_to)


# NFR-4.06: transparency on AI usage and cost drivers
@router.get("/usage", response_model=CoachUsage)
def usage(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    s = get_settings()
    org_users = db.query(User.id).filter(User.org_id == current_user.org_id)
    sessions = db.query(ChatSession.id).filter(ChatSession.user_id.in_(org_users))
    agg = db.query(
        func.count(ChatMessage.id), func.coalesce(func.sum(ChatMessage.tokens_in), 0),
        func.coalesce(func.sum(ChatMessage.tokens_out), 0),
    ).filter(ChatMessage.session_id.in_(sessions)).one()

    by_source: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for r in db.query(Recommendation).filter(Recommendation.org_id == current_user.org_id).all():
        if r.source:
            by_source[r.source.value] = by_source.get(r.source.value, 0) + 1
        if r.status:
            by_status[r.status.value] = by_status.get(r.status.value, 0) + 1

    return CoachUsage(
        model=s.model, ai_enabled=bool(s.openai_api_key),
        chat_sessions=sessions.count(), chat_messages=agg[0], tokens_in=int(agg[1]), tokens_out=int(agg[2]),
        recommendations_by_source=by_source, recommendations_by_status=by_status,
    )
