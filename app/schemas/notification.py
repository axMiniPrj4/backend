from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    title: str
    body: str | None = None
    link_url: str | None = None
    project_id: int | None = None
    task_id: int | None = None
    actor_id: int | None = None
    read_at: datetime | None = None
    created_at: datetime
    is_read: bool = False


class UnreadCountResponse(BaseModel):
    count: int = Field(ge=0)
