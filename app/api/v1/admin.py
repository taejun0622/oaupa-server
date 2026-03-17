from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_superadmin
from app.db.session import get_db
from app.models.oauth_connection import OAuthConnection
from app.models.project import Project
from app.models.user import User
from app.schemas.admin import AdminStatsResponse, AdminUserResponse

router = APIRouter()


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_superadmin),
):
    result = await db.execute(select(User))
    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "is_active": u.is_active,
            "created_at": u.created_at,
        }
        for u in result.scalars().all()
    ]


@router.get("/stats", response_model=AdminStatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_superadmin),
):
    users_count = await db.scalar(select(func.count()).select_from(User))
    projects_count = await db.scalar(select(func.count()).select_from(Project))
    connections_count = await db.scalar(select(func.count()).select_from(OAuthConnection))

    return {
        "users": users_count,
        "projects": projects_count,
        "connections": connections_count,
    }
