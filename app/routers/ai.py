from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.errors import not_found
from app.db.base import utcnow
from app.db.session import get_db
from app.models import AiMessage, AiThread, User
from app.schemas.collaboration import (
    AiMessageCreate,
    AiMessageOut,
    AiMessagePairOut,
    AiThreadCreate,
    AiThreadOut,
    AiUsageOut,
)
from app.services.openai_chat import generate_assistant_reply, is_openai_configured

router = APIRouter(prefix="/api/ai", tags=["AI"])

_MOCK_NO_KEY = (
    "(가응답) OPENAI_API_KEY가 설정되지 않아 더미 응답입니다. "
    "백엔드 .env에 키를 넣으면 실제 답변이 생성됩니다."
)
_MOCK_API_FAIL = (
    "(가응답) OpenAI API 호출에 실패했습니다. "
    "키·모델·네트워크를 확인한 뒤 다시 시도해 주세요."
)


def _get_owned_thread(db: Session, thread_id: int, user_id: int) -> AiThread:
    thread = db.scalar(select(AiThread).where(AiThread.id == thread_id, AiThread.user_id == user_id))
    if thread is None:
        raise not_found("대화를 찾을 수 없습니다.")
    return thread


def _load_messages(db: Session, thread_id: int) -> list[AiMessage]:
    return list(
        db.scalars(
            select(AiMessage)
            .where(AiMessage.thread_id == thread_id)
            .order_by(AiMessage.created_at.asc(), AiMessage.id.asc())
        ).all()
    )


def _to_thread_out(db: Session, thread: AiThread, *, include_messages: bool = False) -> AiThreadOut:
    messages = _load_messages(db, thread.id) if include_messages else []
    return AiThreadOut(
        id=thread.id,
        user_id=thread.user_id,
        title=thread.title,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        messages=[AiMessageOut.model_validate(m) for m in messages],
    )


def _today_start() -> datetime:
    now = utcnow()
    return datetime(now.year, now.month, now.day)


@router.get("/status")
def get_ai_status(user: User = Depends(get_current_user)):
    """프론트 연결 배지용 — 키 존재 여부만 (값은 노출하지 않음)."""
    _ = user
    return {
        "configured": is_openai_configured(),
        "model": get_settings().openai_model if is_openai_configured() else None,
    }


@router.get("/usage", response_model=AiUsageOut)
def get_usage(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Free 플랜 일일 메시지 한도용 — 오늘 role=user 메시지 수."""
    count = db.scalar(
        select(func.count(AiMessage.id))
        .join(AiThread, AiThread.id == AiMessage.thread_id)
        .where(
            AiThread.user_id == user.id,
            AiThread.deleted_at.is_(None),
            AiMessage.role == "user",
            AiMessage.created_at >= _today_start(),
        )
    )
    return AiUsageOut(today_user_messages=int(count or 0))


@router.get("/threads", response_model=list[AiThreadOut])
def list_threads(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    threads = db.scalars(
        select(AiThread)
        .where(AiThread.user_id == user.id)
        .order_by(AiThread.updated_at.desc(), AiThread.id.desc())
    ).all()
    return [_to_thread_out(db, t) for t in threads]


@router.post("/threads", response_model=AiThreadOut, status_code=201)
def create_thread(
    body: AiThreadCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    thread = AiThread(user_id=user.id, title=body.title)
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return _to_thread_out(db, thread)


@router.get("/threads/{thread_id}", response_model=AiThreadOut)
def get_thread(thread_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    thread = _get_owned_thread(db, thread_id, user.id)
    return _to_thread_out(db, thread, include_messages=True)


@router.delete("/threads/{thread_id}", status_code=204)
def delete_thread(thread_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    thread = _get_owned_thread(db, thread_id, user.id)
    thread.soft_delete()
    db.commit()


@router.post("/threads/{thread_id}/messages", response_model=AiMessagePairOut, status_code=201)
def post_message(
    thread_id: int,
    body: AiMessageCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    thread = _get_owned_thread(db, thread_id, user.id)
    history = [
        {"role": m.role, "content": m.content}
        for m in _load_messages(db, thread.id)[-12:]
    ]
    generated = generate_assistant_reply(body.content, history)
    if generated:
        reply = generated
    elif is_openai_configured():
        reply = _MOCK_API_FAIL
    else:
        reply = _MOCK_NO_KEY

    user_msg = AiMessage(thread_id=thread.id, role="user", content=body.content)
    assistant_msg = AiMessage(thread_id=thread.id, role="assistant", content=reply)
    db.add(user_msg)
    db.add(assistant_msg)

    # 첫 사용자 메시지로 제목 갱신
    if not history and (not thread.title or thread.title in {"새 대화", "New chat"}):
        text = body.content.strip().replace("\n", " ")
        thread.title = (text[:40] + "…") if len(text) > 40 else (text or thread.title)

    thread.updated_at = utcnow()
    db.commit()
    db.refresh(user_msg)
    db.refresh(assistant_msg)
    return AiMessagePairOut(
        user_message=AiMessageOut.model_validate(user_msg),
        assistant_message=AiMessageOut.model_validate(assistant_msg),
    )
