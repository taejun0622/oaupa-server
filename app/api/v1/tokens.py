import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.project import Project
from app.models.user import User
from app.schemas.connection import TokenRetrievalResponse
from app.services import billing_service, token_vault_service
from app.services.webhook_event_service import fire_webhook_event

router = APIRouter()


async def _get_project_owner(db: AsyncSession, project: Project) -> User:
    result = await db.execute(select(User).where(User.id == project.user_id))
    return result.scalar_one()


@router.get(
    "/projects/{project_id}/tokens/{connection_id}",
    response_model=TokenRetrievalResponse,
)
async def get_token(
    project_id: uuid.UUID,
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    api_key_project: tuple[ApiKey, Project] = Depends(require_scope("tokens:read")),
):
    _api_key, project = api_key_project
    if project.id != project_id:
        from app.core.exceptions import ForbiddenError
        raise ForbiddenError("API key does not match project")

    # Enforce retrieval limit
    owner = await _get_project_owner(db, project)
    await billing_service.check_retrieval_limit(db, owner)

    result = await token_vault_service.get_token(db, project_id, connection_id)

    # Track usage + fire event
    await billing_service.track_token_retrieval(db, project_id)
    await fire_webhook_event(db, project_id, "token.retrieved", {
        "connection_id": str(connection_id),
        "provider": result.provider,
    })

    response = JSONResponse(content=result.model_dump(mode="json"))
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get(
    "/projects/{project_id}/tokens",
    response_model=TokenRetrievalResponse,
)
async def get_token_by_provider(
    project_id: uuid.UUID,
    provider: str = Query(...),
    db: AsyncSession = Depends(get_db),
    api_key_project: tuple[ApiKey, Project] = Depends(require_scope("tokens:read")),
):
    _api_key, project = api_key_project
    if project.id != project_id:
        from app.core.exceptions import ForbiddenError
        raise ForbiddenError("API key does not match project")

    # Enforce retrieval limit
    owner = await _get_project_owner(db, project)
    await billing_service.check_retrieval_limit(db, owner)

    result = await token_vault_service.get_token_by_provider(db, project_id, provider)

    # Track usage + fire event
    await billing_service.track_token_retrieval(db, project_id)
    await fire_webhook_event(db, project_id, "token.retrieved", {
        "connection_id": str(result.connection_id),
        "provider": result.provider,
    })

    response = JSONResponse(content=result.model_dump(mode="json"))
    response.headers["Cache-Control"] = "no-store"
    return response
