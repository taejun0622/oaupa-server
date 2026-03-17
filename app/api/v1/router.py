from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.projects import router as projects_router
from app.api.v1.api_keys import router as api_keys_router
from app.api.v1.oauth import router as oauth_router
from app.api.v1.connections import router as connections_router
from app.api.v1.tokens import router as tokens_router
from app.api.v1.billing import router as billing_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.admin import router as admin_router

api_v1_router = APIRouter()

api_v1_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_v1_router.include_router(users_router, prefix="/users", tags=["users"])
api_v1_router.include_router(projects_router, prefix="/projects", tags=["projects"])
api_v1_router.include_router(api_keys_router, tags=["api-keys"])
api_v1_router.include_router(oauth_router, prefix="/oauth", tags=["oauth"])
api_v1_router.include_router(connections_router, tags=["connections"])
api_v1_router.include_router(tokens_router, tags=["tokens"])
api_v1_router.include_router(billing_router, prefix="/billing", tags=["billing"])
api_v1_router.include_router(webhooks_router, tags=["webhooks"])
api_v1_router.include_router(admin_router, prefix="/admin", tags=["admin"])
