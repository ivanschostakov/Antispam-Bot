from .group_admin import router as group_admin_router
from .group_user import router as group_user_router
from .private_admin import router as private_admin_router

__all__ = ["group_user_router", "group_admin_router", "private_admin_router"]
