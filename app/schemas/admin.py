import uuid
from datetime import datetime

from pydantic import BaseModel


class AdminUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    created_at: datetime | None


class AdminStatsResponse(BaseModel):
    users: int
    projects: int
    connections: int
