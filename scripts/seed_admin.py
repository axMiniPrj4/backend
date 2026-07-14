"""초기 SYSTEM_ADMIN 시드 스크립트 — 가입 API로는 관리자 생성 불가.

사용: python -m scripts.seed_admin [login_id] [password] [email]
기본값: admin / admin1234! / admin@ohapjijol.io (운영에서는 반드시 인자로 지정)
"""
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User
from app.models.user import UserRole


def main() -> None:
    login_id = sys.argv[1] if len(sys.argv) > 1 else "admin"
    password = sys.argv[2] if len(sys.argv) > 2 else "admin1234!"
    email = sys.argv[3] if len(sys.argv) > 3 else "admin@ohapjijol.io"

    with SessionLocal() as db:
        exists = db.scalar(
            select(User.id).where(User.login_id == login_id).execution_options(include_deleted=True)
        )
        if exists:
            print(f"이미 존재하는 login_id입니다: {login_id}")
            return
        admin = User(
            login_id=login_id,
            password_hash=hash_password(password),
            name="시스템관리자",
            nickname=f"admin_{login_id}",
            email=email,
            role=UserRole.SYSTEM_ADMIN,
        )
        db.add(admin)
        db.commit()
        print(f"SYSTEM_ADMIN 생성 완료: id={admin.id}, login_id={login_id}")


if __name__ == "__main__":
    main()
