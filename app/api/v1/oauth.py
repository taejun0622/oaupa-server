from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.oauth_provider import OAuthProvider
from app.models.oauth_state import OAuthState
from app.models.user import User
from app.schemas.oauth import OAuthAuthorizeRequest, OAuthAuthorizeResponse, ProviderResponse
from app.services import oauth_service

router = APIRouter()


@router.get("/providers", response_model=list[ProviderResponse])
async def list_providers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(OAuthProvider).where(OAuthProvider.is_active.is_(True))
    )
    return result.scalars().all()


@router.get("/providers/{provider_id}", response_model=ProviderResponse)
async def get_provider(provider_id: str, db: AsyncSession = Depends(get_db)):
    from app.core.exceptions import NotFoundError

    result = await db.execute(
        select(OAuthProvider).where(
            OAuthProvider.id == provider_id, OAuthProvider.is_active.is_(True)
        )
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        raise NotFoundError("Provider not found")
    return provider


@router.post("/authorize", response_model=OAuthAuthorizeResponse)
async def authorize(
    data: OAuthAuthorizeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await oauth_service.start_oauth_flow(db, user.id, data)


@router.get("/callback")
async def callback(
    state: str = Query(...),
    code: str | None = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    # Handle OAuth provider errors (e.g., user denied access)
    if error:
        # Look up state to get redirect_uri even on error
        result = await db.execute(
            select(OAuthState).where(OAuthState.state_token == state)
        )
        oauth_state = result.scalar_one_or_none()
        if oauth_state and oauth_state.redirect_uri:
            redirect_uri = oauth_state.redirect_uri
            separator = "&" if "?" in redirect_uri else "?"
            redirect_uri = f"{redirect_uri}{separator}error={error}"
            if error_description:
                from urllib.parse import quote
                redirect_uri = f"{redirect_uri}&error_description={quote(error_description)}"
            return RedirectResponse(url=redirect_uri)
        from app.core.exceptions import BadRequestError
        raise BadRequestError(f"OAuth error: {error} - {error_description or ''}")

    if code is None:
        from app.core.exceptions import BadRequestError
        raise BadRequestError("Missing authorization code")

    _connection, redirect_uri = await oauth_service.handle_oauth_callback(db, code, state)
    return RedirectResponse(url=redirect_uri)
