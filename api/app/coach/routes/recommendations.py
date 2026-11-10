from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.app.core.database import get_db
from api.app.core.deps import get_current_user
from api.app.core.enums import RecSource, RecStatus, Scope
from api.app.core.models import User

from ..deps import require_manager
from ..llm import LLMClient, get_llm
from ..schemas import GenerateRequest, GenerateResponse, RecommendationOut, StatusUpdate
from ..services import recommendation_service as svc

router = APIRouter(prefix="/coach/recommendations", tags=["S4 Coach - Recommendations"])


# FR-4.03 / FR-4.04 / FR-4.05
@router.post("/generate", response_model=GenerateResponse, status_code=201)
def generate_recommendations(
    body: GenerateRequest = GenerateRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
    llm: Optional[LLMClient] = Depends(get_llm),
):
    return svc.generate(db, current_user, llm, body.mode)


# FR-4.06
@router.get("", response_model=List[RecommendationOut])
def list_recommendations(
    status: Optional[RecStatus] = None,
    scope: Optional[Scope] = None,
    department_id: Optional[UUID] = None,
    source: Optional[RecSource] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.list_recommendations(db, current_user, status, scope, department_id, source)


@router.get("/{rec_id}", response_model=RecommendationOut)
def get_recommendation(rec_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return svc.get_recommendation(db, current_user, rec_id)


# FR-4.07
@router.patch("/{rec_id}/status", response_model=RecommendationOut)
def update_status(
    rec_id: UUID,
    body: StatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    return svc.update_status(db, current_user, rec_id, body.status)
