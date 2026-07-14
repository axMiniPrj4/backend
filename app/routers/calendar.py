from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import ProjectContext, get_project_context
from app.core.errors import not_found
from app.db.session import get_db
from app.models import CalendarEvent
from app.schemas.collaboration import CalendarEventCreate, CalendarEventOut, CalendarEventUpdate

router = APIRouter(prefix="/api/projects/{project_id}/calendar", tags=["Calendar"])


def _get_event(db: Session, ctx: ProjectContext, event_id: int) -> CalendarEvent:
    event = db.scalar(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id, CalendarEvent.project_id == ctx.project.id
        )
    )
    if event is None:
        raise not_found("일정을 찾을 수 없습니다.")
    return event


@router.get("/events", response_model=list[CalendarEventOut])
def list_calendar_events(
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(CalendarEvent)
        .where(CalendarEvent.project_id == ctx.project.id)
        .order_by(CalendarEvent.event_date.asc(), CalendarEvent.id.asc())
    ).all()


@router.post("/events", response_model=CalendarEventOut, status_code=201)
def create_calendar_event(
    body: CalendarEventCreate,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    event = CalendarEvent(
        project_id=ctx.project.id,
        title=body.title,
        event_date=body.event_date,
        event_time=body.event_time,
        description=body.description,
        created_by=ctx.user.id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.patch("/events/{event_id}", response_model=CalendarEventOut)
def update_calendar_event(
    event_id: int,
    body: CalendarEventUpdate,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    event = _get_event(db, ctx, event_id)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(event, field, value)
    db.commit()
    db.refresh(event)
    return event


@router.delete("/events/{event_id}", status_code=204)
def delete_calendar_event(
    event_id: int,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    event = _get_event(db, ctx, event_id)
    db.delete(event)
    db.commit()
