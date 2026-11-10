from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.app.core.database import get_db
from api.app.core.deps import get_current_user
from api.app.core.enums import UserRole
from api.app.core.models import User

from ..schemas import RecommendationOut, WhatIfRequest, WhatIfResponse
from ..services import whatif_service as svc

router = APIRouter(prefix="/coach/what-if", tags=["S4 Coach - What-if"])


@router.get("/scenarios")
def scenarios(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return svc.list_scenarios(db, current_user.org_id)


# FR-4.07: simulate with S2's engine; optionally save as a recommendation
@router.post("", response_model=WhatIfResponse)
def run_scenario(body: WhatIfRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if body.save and current_user.role not in (UserRole.admin, UserRole.manager):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Manager or admin role required to save a recommendation.")
    result = svc.run(db, current_user, body.scenario_id, body.change_pct)
    saved = svc.save_as_recommendation(db, current_user, result) if body.save else None
    return WhatIfResponse(result=result, saved_recommendation=RecommendationOut.model_validate(saved) if saved else None)
