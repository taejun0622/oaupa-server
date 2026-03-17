import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, UnauthorizedError
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserRegister
from app.services import user_service


@pytest.mark.asyncio
class TestRegisterUser:
    async def test_success(self, db: AsyncSession):
        email = f"svc-{uuid.uuid4().hex[:8]}@test.com"
        data = UserRegister(email=email, password="securepass", full_name="Test")
        user = await user_service.register_user(db, data)
        assert user.email == email
        assert user.full_name == "Test"
        assert user.id is not None

    async def test_duplicate_email(self, db: AsyncSession):
        email = f"dup-{uuid.uuid4().hex[:8]}@test.com"
        data = UserRegister(email=email, password="pass")
        await user_service.register_user(db, data)
        with pytest.raises(ConflictError):
            await user_service.register_user(db, data)


@pytest.mark.asyncio
class TestAuthenticateUser:
    async def test_success(self, db: AsyncSession):
        email = f"auth-{uuid.uuid4().hex[:8]}@test.com"
        data = UserRegister(email=email, password="correct123")
        await user_service.register_user(db, data)
        tokens = await user_service.authenticate_user(db, email, "correct123")
        assert tokens.access_token
        assert tokens.refresh_token

    async def test_wrong_password(self, db: AsyncSession):
        email = f"wrongpw-{uuid.uuid4().hex[:8]}@test.com"
        data = UserRegister(email=email, password="correct123")
        await user_service.register_user(db, data)
        with pytest.raises(UnauthorizedError):
            await user_service.authenticate_user(db, email, "wrong")

    async def test_nonexistent_email(self, db: AsyncSession):
        with pytest.raises(UnauthorizedError):
            await user_service.authenticate_user(db, "nobody@test.com", "pass")

    async def test_inactive_user(self, db: AsyncSession):
        email = f"inactive-{uuid.uuid4().hex[:8]}@test.com"
        user = User(
            email=email,
            password_hash=hash_password("pass"),
            is_active=False,
        )
        db.add(user)
        await db.flush()
        with pytest.raises(UnauthorizedError):
            await user_service.authenticate_user(db, email, "pass")


@pytest.mark.asyncio
class TestRefreshTokens:
    async def test_valid_refresh(self, db: AsyncSession):
        email = f"ref-{uuid.uuid4().hex[:8]}@test.com"
        data = UserRegister(email=email, password="pass")
        await user_service.register_user(db, data)
        tokens = await user_service.authenticate_user(db, email, "pass")
        new_tokens = await user_service.refresh_tokens(db, tokens.refresh_token)
        assert new_tokens.access_token
        assert new_tokens.refresh_token

    async def test_invalid_refresh_token(self, db: AsyncSession):
        with pytest.raises(UnauthorizedError):
            await user_service.refresh_tokens(db, "garbage")


@pytest.mark.asyncio
class TestChangePassword:
    async def test_success(self, db: AsyncSession, test_user: User):
        await user_service.change_password(db, test_user, "testpassword123", "newpass456")
        from app.core.security import verify_password
        assert verify_password("newpass456", test_user.password_hash)

    async def test_wrong_current(self, db: AsyncSession, test_user: User):
        with pytest.raises(BadRequestError):
            await user_service.change_password(db, test_user, "wrong", "new")


@pytest.mark.asyncio
class TestUpdateUser:
    async def test_update_name(self, db: AsyncSession, test_user: User):
        updated = await user_service.update_user(db, test_user, "New Name")
        assert updated.full_name == "New Name"

    async def test_update_none(self, db: AsyncSession, test_user: User):
        original = test_user.full_name
        await user_service.update_user(db, test_user, None)
        assert test_user.full_name == original
