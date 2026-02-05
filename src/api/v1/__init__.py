"""API v1 router configuration."""

from fastapi import APIRouter

from api.v1.routes.activity import router as activity_router
from api.v1.routes.groups import router as groups_router
from api.v1.routes.invitations import invitations_router, workspace_invitations_router
from api.v1.routes.notifications import (
    user_notifications_router,
    workspace_notifications_router,
)
from api.v1.routes.tags import router as tags_router
from api.v1.routes.tags import todos_tags_router
from api.v1.routes.todos import router as todos_router
from api.v1.routes.workspaces import router as workspaces_router

router = APIRouter()
router.include_router(todos_router)
router.include_router(tags_router)
router.include_router(todos_tags_router)
router.include_router(workspaces_router)
router.include_router(workspace_invitations_router)
router.include_router(invitations_router)
router.include_router(workspace_notifications_router)
router.include_router(user_notifications_router)
router.include_router(activity_router)
router.include_router(groups_router)
