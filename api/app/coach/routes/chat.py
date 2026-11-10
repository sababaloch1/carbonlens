from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from api.app.core.database import get_db
from api.app.core.deps import get_current_user
from api.app.core.models import User

from ..llm import LLMClient, get_llm
from ..schemas import ChatMessageIn, ChatMessageOut, ChatReply, ChatSessionCreate, ChatSessionOut
from ..services import chat_service as svc

router = APIRouter(prefix="/coach/chat", tags=["S4 Coach - Chat Assistant"])


@router.post("/sessions", response_model=ChatSessionOut, status_code=201)
def create_session(
    body: ChatSessionCreate = ChatSessionCreate(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.create_session(db, current_user, body.title)


@router.get("/sessions", response_model=List[ChatSessionOut])
def list_sessions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return svc.list_sessions(db, current_user)


@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessageOut])
def get_messages(session_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return svc.get_messages(db, svc.get_session(db, current_user, session_id))


# FR-4.08
@router.post("/sessions/{session_id}/messages", response_model=ChatReply)
def send_message(
    session_id: UUID,
    body: ChatMessageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    llm: Optional[LLMClient] = Depends(get_llm),
):
    return svc.send_message(db, current_user, llm, session_id, body.content)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc.delete_session(db, current_user, session_id)
    return None
