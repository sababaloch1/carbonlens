"""S4 - Role checks (NFR-4.04)."""
from fastapi import Depends, HTTPException, status

from api.app.core.deps import get_current_user
from api.app.core.enums import UserRole
from api.app.core.models import User


def require_manager(current_user: User = Depends(get_current_user)) -> User:
    """Managers and admins may generate recommendations, change their status and approve content."""
    if current_user.role not in (UserRole.admin, UserRole.manager):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Manager or admin role required.")
    return current_user
