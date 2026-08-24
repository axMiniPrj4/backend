"""아바타 풀 할당 단위 테스트."""
from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User
from app.services.avatar_service import AVATAR_KEYS, pick_avatar_key


def _add_user(db, login_id: str, avatar_key: str | None = None):
    user = User(
        login_id=login_id,
        password_hash=hash_password("password1!"),
        name="테스트",
        nickname=f"nick_{login_id}",
        email=f"{login_id}@test.io",
        avatar_key=avatar_key,
    )
    db.add(user)
    db.commit()
    return user


def test_pick_avatar_unique_until_pool_exhausted():
    with SessionLocal() as db:
        assigned = []
        for i in range(len(AVATAR_KEYS)):
            key = pick_avatar_key(db)
            assert key in AVATAR_KEYS
            assert key not in assigned
            assigned.append(key)
            _add_user(db, f"pool_user_{i:02d}", avatar_key=key)

        duplicate_ok = pick_avatar_key(db)
        assert duplicate_ok in AVATAR_KEYS


def test_pick_avatar_reuses_after_user_leaves_pool():
    with SessionLocal() as db:
        for i, key in enumerate(AVATAR_KEYS):
            _add_user(db, f"full_user_{i:02d}", avatar_key=key)

        freed = db.scalar(select(User).where(User.login_id == "full_user_00"))
        freed.soft_delete()
        db.commit()

        key = pick_avatar_key(db)
        assert key == "01-fox"
