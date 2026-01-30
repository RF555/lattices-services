"""API v1 router configuration."""

from fastapi import APIRouter

from api.v1.routes.tags import router as tags_router, todos_tags_router
from api.v1.routes.todos import router as todos_router

router = APIRouter()
router.include_router(todos_router)
router.include_router(tags_router)
router.include_router(todos_tags_router)
