#!/usr/bin/env python3
"""소프트 삭제된 자료의 남은 업로드 파일 정리.

자료실 삭제는 행만 soft delete 하고 파일은 디스크에 그대로 둔다
(routers/archive.py: delete_archive_doc). 업로드 한도가 500MB 라서
그냥 두면 지운 자료의 용량이 계속 묶인다.

자료실에는 복원 기능이 없어(workspace 파일에만 있다) 소프트 삭제는 사실상
영구지만, 실수 삭제에 대한 완충으로 유예 기간을 둔다. 기간이 지난 파일만 지운다.

기본은 dry-run 이다. 실제로 지우려면 --apply 를 명시해야 한다.

    # 무엇이 지워질지 확인 (아무것도 지우지 않음)
    docker exec -w /app -e PYTHONPATH=/app ohapjijol-backend \\
        python scripts/cleanup_orphan_files.py

    # 90일 유예로 확인
    docker exec -w /app -e PYTHONPATH=/app ohapjijol-backend \\
        python scripts/cleanup_orphan_files.py --days 90

    # 실제 삭제
    docker exec -w /app -e PYTHONPATH=/app ohapjijol-backend \\
        python scripts/cleanup_orphan_files.py --apply

안전 장치
- 같은 stored_name 을 살아있는 행이 하나라도 쓰고 있으면 건너뛴다
  (한 파일을 여러 행이 가리키는 경우 방어)
- 문의 첨부(inquiry.stored_name)가 가리키는 파일도 건너뛴다
- DB 가 참조하지 않는 파일은 손대지 않는다. 업로드 롤백이 정상 동작하므로
  이 부류는 원래 생기지 않으며, 생겼다면 원인을 먼저 확인해야 한다
- 삭제 내역은 uploads/_cleanup-log/ 아래에 남긴다
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta

from sqlalchemy import text

from app.core.config import settings
from app.db.base import utcnow
from app.db.session import SessionLocal

DEFAULT_GRACE_DAYS = 30
LOG_DIRNAME = "_cleanup-log"


def human(size: int) -> str:
    mb = size / 1024 / 1024
    return f"{mb:.2f}MB" if mb >= 0.01 else f"{size}B"


def main() -> int:
    parser = argparse.ArgumentParser(description="소프트 삭제된 자료의 업로드 파일 정리")
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_GRACE_DAYS,
        help=f"유예 기간(일). 이보다 오래된 삭제만 정리한다 (기본 {DEFAULT_GRACE_DAYS})",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="실제로 파일을 삭제한다. 없으면 dry-run",
    )
    args = parser.parse_args()

    if args.days < 0:
        print("--days 는 0 이상이어야 합니다.", file=sys.stderr)
        return 2

    upload_dir = str(settings.upload_dir)
    cutoff = utcnow() - timedelta(days=args.days)

    db = SessionLocal()
    try:
        # ORM 의 soft delete 필터를 우회해야 하므로 raw SQL 로 읽는다
        live = {
            row[0]
            for row in db.execute(text("SELECT stored_name FROM doc_version WHERE deleted_at IS NULL"))
            if row[0]
        }
        inquiry_files = {
            row[0]
            for row in db.execute(text("SELECT stored_name FROM inquiry WHERE stored_name IS NOT NULL"))
            if row[0]
        }
        dead_rows = db.execute(
            text(
                "SELECT stored_name, doc_id, file_name, deleted_at "
                "FROM doc_version WHERE deleted_at IS NOT NULL ORDER BY deleted_at"
            )
        ).all()
    finally:
        db.close()

    targets: list[tuple[str, int, str, object, int]] = []
    skipped_live = 0
    skipped_recent = 0
    skipped_missing = 0
    skipped_inquiry = 0
    seen: set[str] = set()

    for stored_name, doc_id, file_name, deleted_at in dead_rows:
        if not stored_name or stored_name in seen:
            continue
        seen.add(stored_name)

        if stored_name in live:
            # 같은 파일을 아직 살아있는 행이 쓰고 있다 — 절대 지우지 않는다
            skipped_live += 1
            continue
        if stored_name in inquiry_files:
            skipped_inquiry += 1
            continue
        if deleted_at is None or deleted_at > cutoff:
            skipped_recent += 1
            continue

        path = os.path.join(upload_dir, stored_name)
        if not os.path.isfile(path):
            # 이미 사라진 파일 — DB 행만 남은 경우. 조용히 넘긴다
            skipped_missing += 1
            continue

        targets.append((stored_name, doc_id, file_name, deleted_at, os.path.getsize(path)))

    total_bytes = sum(item[4] for item in targets)
    mode = "삭제 실행" if args.apply else "DRY-RUN (아무것도 지우지 않음)"
    print(f"=== 업로드 파일 정리 · {mode} ===")
    print(f"  업로드 경로   {upload_dir}")
    print(f"  유예 기간     {args.days}일 (기준 {cutoff:%Y-%m-%d %H:%M} UTC 이전 삭제분)")
    print()
    print(f"  정리 대상     {len(targets)}개  {human(total_bytes)}")
    print(f"  건너뜀        살아있는 참조 {skipped_live} · 유예 기간 내 {skipped_recent} · "
          f"파일 없음 {skipped_missing} · 문의 첨부 {skipped_inquiry}")
    print()

    if not targets:
        print("  정리할 파일이 없습니다.")
        return 0

    for stored_name, doc_id, file_name, deleted_at, size in targets:
        print(f"  {human(size):>10}  doc {doc_id:<5} {file_name[:45]:<45} 삭제 {deleted_at:%Y-%m-%d}")

    if not args.apply:
        print()
        print("  실제로 지우려면 --apply 를 붙여 다시 실행하세요.")
        return 0

    log_dir = os.path.join(upload_dir, LOG_DIRNAME)
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"cleanup-{utcnow():%Y%m%d-%H%M%S}.log")

    removed = 0
    freed = 0
    failed: list[tuple[str, str]] = []
    with open(log_path, "w", encoding="utf-8") as log:
        log.write(f"# cleanup at {utcnow():%Y-%m-%d %H:%M:%S} UTC, grace {args.days}d\n")
        for stored_name, doc_id, file_name, deleted_at, size in targets:
            path = os.path.join(upload_dir, stored_name)
            try:
                os.remove(path)
            except OSError as exc:
                failed.append((stored_name, str(exc)))
                log.write(f"FAIL\t{stored_name}\t{exc}\n")
                continue
            removed += 1
            freed += size
            log.write(f"OK\t{stored_name}\tdoc={doc_id}\t{file_name}\tdeleted_at={deleted_at}\n")

    print()
    print(f"  삭제 {removed}개 · 확보 {human(freed)}")
    if failed:
        print(f"  실패 {len(failed)}개:")
        for stored_name, reason in failed[:10]:
            print(f"    {stored_name} — {reason}")
    print(f"  기록: {log_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
