from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from api.app.core.database import get_db
from api.app.core.deps import get_current_user
from api.app.core.enums import ContentStatus, UserRole
from api.app.core.models import User

from ..deps import require_manager
from ..llm import LLMClient, get_llm
from ..schemas import LearningGenerate, LearningOut
from ..services import learning_service as svc

router = APIRouter(prefix="/coach/learning", tags=["S4 Coach - Learning Content"])


# FR-4.09
@router.post("/generate", response_model=LearningOut, status_code=201)
def generate_content(
    body: LearningGenerate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
    llm: Optional[LLMClient] = Depends(get_llm),
):
    return svc.generate(db, llm, body.topic, body.audience)


@router.get("", response_model=List[LearningOut])
def list_content(
    audience: Optional[UserRole] = None,
    status: Optional[ContentStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.list_content(db, current_user, audience, status)


@router.get("/{content_id}", response_model=LearningOut)
def get_content(content_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return svc.get_content(db, current_user, content_id)


# FR-4.10
@router.post("/{content_id}/approve", response_model=LearningOut)
def approve_content(content_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(require_manager)):
    return svc.approve(db, content_id)


@router.delete("/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_content(content_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(require_manager)):
    svc.delete(db, content_id)
    return None
