from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ChatMessageCreate(BaseModel):
    type: str = Field(default="text", pattern="^(text|emoji|image)$")
    content: str | None = None
    image_data: str | None = None
    file_name: str | None = None


class ChatMessageOut(ORMModel):
    id: int
    project_id: int
    author_id: int
    type: str
    content: str | None
    image_data: str | None
    file_name: str | None
    created_at: datetime


class WhiteboardUpdate(BaseModel):
    objects: list = Field(default_factory=list)
    size_key: str = "square"
    custom_width: int = 1280
    custom_height: int = 720
    zoom: float = 1.0


class WhiteboardOut(ORMModel):
    project_id: int
    objects: list
    size_key: str
    custom_width: int
    custom_height: int
    zoom: float
    updated_at: datetime


class WorkspaceFileCreate(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    language: str | None = None
    content: str = ""


class WorkspaceFileUpdate(BaseModel):
    content: str


class WorkspaceFileRestore(BaseModel):
    version_id: int


class WorkspaceFileOut(ORMModel):
    id: int
    project_id: int
    path: str
    language: str
    content: str
    version: int
    updated_by: int
    updated_at: datetime


class WorkspaceFileVersionOut(ORMModel):
    id: int
    file_id: int
    version: int
    content: str
    saved_by: int
    saved_at: datetime


class ErdUpdate(BaseModel):
    dbml: str = ""
    positions: dict = Field(default_factory=dict)
    zoom: float = 1.0
    split_percent: int = 36


class ErdOut(ORMModel):
    project_id: int
    dbml: str
    positions: dict
    zoom: float
    split_percent: int
    updated_at: datetime


class VideoSessionUpdate(BaseModel):
    joined: bool | None = None
    muted: bool | None = None
    camera_off: bool | None = None
    started_at: datetime | None = None


class VideoSessionOut(ORMModel):
    project_id: int
    joined: bool
    muted: bool
    camera_off: bool
    started_at: datetime | None
    updated_at: datetime


class VideoPeerIn(BaseModel):
    peer_id: str = Field(min_length=1, max_length=120)
    nickname: str = Field(default="", max_length=100)
    muted: bool = False
    camera_off: bool = False


class VideoPeerOut(BaseModel):
    peer_id: str
    nickname: str
    muted: bool
    camera_off: bool


class VideoSignalIn(BaseModel):
    to_peer_id: str = Field(min_length=1, max_length=120)
    type: str = Field(pattern="^(offer|answer|candidate|bye)$")
    payload: dict = Field(default_factory=dict)


class VideoSignalOut(BaseModel):
    from_peer_id: str
    type: str
    payload: dict


class AiThreadCreate(BaseModel):
    title: str = Field(default="새 대화", min_length=1, max_length=200)


class AiMessageCreate(BaseModel):
    content: str = Field(min_length=1)


class AiMessageOut(ORMModel):
    id: int
    thread_id: int
    role: str
    content: str
    created_at: datetime


class AiThreadOut(ORMModel):
    id: int
    user_id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[AiMessageOut] = Field(default_factory=list)


class AiUsageOut(BaseModel):
    today_user_messages: int


class AiMessagePairOut(BaseModel):
    user_message: AiMessageOut
    assistant_message: AiMessageOut


class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    event_date: date
    event_time: str | None = Field(default=None, max_length=10)
    description: str | None = None


class CalendarEventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    event_date: date | None = None
    event_time: str | None = Field(default=None, max_length=10)
    description: str | None = None


class CalendarEventOut(ORMModel):
    id: int
    project_id: int
    title: str
    event_date: date
    event_time: str | None
    description: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime
