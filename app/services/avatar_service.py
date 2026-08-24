"""회원가입 시 캐릭터 아바타 키 할당.

- 활성(미탈퇴) 사용자에게 아직 쓰이지 않은 키 중 랜덤 선택
- 20종이 모두 사용 중이면 중복 허용 — 전체 풀에서 다시 랜덤
"""
from __future__ import annotations

import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User

AVATAR_KEYS: tuple[str, ...] = (
    "01-fox",
    "02-bear",
    "03-cat",
    "04-rabbit",
    "05-otter",
    "06-penguin",
    "07-shiba",
    "08-raccoon",
    "09-red-panda",
    "10-owl",
    "11-frog",
    "12-capybara",
    "13-panda",
    "14-squirrel",
    "15-duck",
    "16-hamster",
    "17-seal",
    "18-hedgehog",
    "19-koala",
    "20-tiger",
)


def pick_avatar_key(db: Session) -> str:
    used = set(
        db.scalars(
            select(User.avatar_key).where(User.avatar_key.isnot(None))
        ).all()
    )
    available = [key for key in AVATAR_KEYS if key not in used]
    pool = available if available else list(AVATAR_KEYS)
    return random.choice(pool)
