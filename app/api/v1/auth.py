from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import (
    ForgotPasswordRequest,
    MessageResponse,
    ResetPasswordRequest,
    TokenPair,
    TokenRefresh,
    UserLogin,
    UserRegister,
    UserResponse,
    VerifyEmailRequest,
)
from app.services import user_service
from app.services.audit_service import log_action

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=201)
@limiter.limit("3/minute")
async def register(request: Request, data: UserRegister, db: AsyncSession = Depends(get_db)):
    user = await user_service.register_user(db, data)
    await log_action(
        db, "user.registered",
        user_id=user.id,
        resource_type="user",
        resource_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    return user


@router.post("/login", response_model=TokenPair)
@limiter.limit("5/minute")
async def login(request: Request, data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await user_service.authenticate_user(db, data.email, data.password)
    # Log after successful auth — authenticate_user raises on failure
    from sqlalchemy import select
    from app.models.user import User as UserModel
    user_result = await db.execute(select(UserModel).where(UserModel.email == data.email))
    user = user_result.scalar_one()
    await log_action(
        db, "user.login",
        user_id=user.id,
        resource_type="user",
        resource_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    return result


@router.post("/refresh", response_model=TokenPair)
@limiter.limit("10/minute")
async def refresh(request: Request, data: TokenRefresh, db: AsyncSession = Depends(get_db)):
    return await user_service.refresh_tokens(db, data.refresh_token)


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("3/minute")
async def forgot_password(request: Request, data: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    await user_service.request_password_reset(db, data.email)
    return MessageResponse(message="If an account with that email exists, a reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def reset_password(request: Request, data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    await user_service.reset_password(db, data.token, data.new_password)
    return MessageResponse(message="Password has been reset successfully.")


@router.post("/send-verification", response_model=MessageResponse)
@limiter.limit("3/minute")
async def send_verification(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await user_service.send_verification(db, user)
    return MessageResponse(message="Verification email sent.")


@router.post("/verify-email", response_model=MessageResponse)
@limiter.limit("5/minute")
async def verify_email(request: Request, data: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    await user_service.verify_email(db, data.token)
    return MessageResponse(message="Email verified successfully.")
