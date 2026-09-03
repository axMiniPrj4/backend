"""프로젝트 목록의 사용자별 표시 순서.

대시보드 카드 순서는 사람마다 다르게 두고 싶어서 project 에 컬럼을 두지 않고
사용자별 링크 테이블로 뺐다. 여기 없는 프로젝트는 저장된 순서 뒤에 붙이고,
반대로 목록에서 사라진 프로젝트 행은 그냥 무시한다 — 별도 정리가 필요 없다.
"""
from sqlalchemy import ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPK


class UserProjectOrder(Base):
    __tablename__ = "user_project_order"
    __table_args__ = (Index("ix_user_project_order_user", "user_id", "sort_order"),)

    user_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("project.id", ondelete="CASCADE"), primary_key=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
