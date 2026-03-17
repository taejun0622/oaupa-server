import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_project_for_user
from app.db.session import get_db
from app.models.project import Project
from app.schemas.webhook import WebhookCreateResponse, WebhookDeliveryResponse, WebhookResponse, WebhookTestResponse

router = APIRouter()


class WebhookCreateRequest(BaseModel):
    url: str
    events: list[str]


@router.get("/projects/{project_id}/webhooks", response_model=list[WebhookResponse])
async def list_webhooks(
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services import webhook_service
    return await webhook_service.list_webhooks(db, project.id)


@router.post("/projects/{project_id}/webhooks", status_code=201, response_model=WebhookCreateResponse)
async def create_webhook(
    data: WebhookCreateRequest,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services import webhook_service
    return await webhook_service.create_webhook(db, project.id, data.url, data.events)


@router.delete("/projects/{project_id}/webhooks/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: uuid.UUID,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services import webhook_service
    await webhook_service.delete_webhook(db, project.id, webhook_id)


@router.get(
    "/projects/{project_id}/webhooks/{webhook_id}/deliveries",
    response_model=list[WebhookDeliveryResponse],
)
async def list_deliveries(
    webhook_id: uuid.UUID,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services import webhook_service
    return await webhook_service.list_deliveries(db, project.id, webhook_id)


@router.post(
    "/projects/{project_id}/webhooks/{webhook_id}/test",
    response_model=WebhookTestResponse,
)
async def test_webhook(
    webhook_id: uuid.UUID,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services import webhook_service
    delivery = await webhook_service.send_test_event(db, project.id, webhook_id)
    status = "delivered" if delivery.delivered_at else "failed"
    return WebhookTestResponse(delivery_id=delivery.id, status=status)
