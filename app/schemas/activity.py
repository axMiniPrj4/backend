from datetime import datetime

from pydantic import BaseModel


class ActivityItemOut(BaseModel):
    id: str
    type: str  # chat|task|doc|calendar|comment
    user: str
    user_id: int
    message: str
    project_id: int | None = None
    project_name: str | None = None
    icon: str
    created_at: datetime
