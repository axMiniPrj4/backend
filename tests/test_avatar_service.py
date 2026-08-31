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


def _used_keys(db) -> set[str]:
    """현재 살아 있는 사용자가 쓰고 있는 아바타 키 (soft delete 는 세션 필터로 제외)."""
    return {
        key
        for key in db.scalars(select(User.avatar_key).where(User.avatar_key.isnot(None))).all()
        if key
    }


def test_pick_avatar_unique_until_pool_exhausted():
    """빈 자리가 남아 있는 동안에는 겹치지 않게 배정한다.

    같은 세션에서 앞선 테스트가 이미 키를 일부 쓰고 있으므로,
    '20개 전부'가 아니라 '남은 자리 수'만큼만 검사한다.
    """
    with SessionLocal() as db:
        used_before = _used_keys(db)
        remaining = [key for key in AVATAR_KEYS if key not in used_before]

        assigned = []
        for i, _ in enumerate(remaining):
            key = pick_avatar_key(db)
            assert key in AVATAR_KEYS
            assert key not in used_before, "빈 자리가 남았는데 이미 쓰는 키를 골랐다"
            assert key not in assigned, "빈 자리가 남았는데 같은 키를 두 번 골랐다"
            assigned.append(key)
            _add_user(db, f"pool_user_{i:02d}", avatar_key=key)

        assert _used_keys(db) == set(AVATAR_KEYS)
        # 풀이 모두 차면 중복을 허용한다
        assert pick_avatar_key(db) in AVATAR_KEYS


def test_pick_avatar_reuses_after_user_leaves_pool():
    """탈퇴로 자리가 비면 그 키를 다시 배정한다."""
    with SessionLocal() as db:
        # 남은 자리가 있으면 마저 채워 풀을 가득 만든다
        for i, key in enumerate(key for key in AVATAR_KEYS if key not in _used_keys(db)):
            _add_user(db, f"full_user_{i:02d}", avatar_key=key)
        assert _used_keys(db) == set(AVATAR_KEYS)

        # 특정 키를 쓰던 사용자를 모두 탈퇴시키면 그 키만 비게 된다
        target = AVATAR_KEYS[0]
        for user in db.scalars(select(User).where(User.avatar_key == target)).all():
            user.soft_delete()
        db.commit()

        assert target not in _used_keys(db)
        assert pick_avatar_key(db) == target
