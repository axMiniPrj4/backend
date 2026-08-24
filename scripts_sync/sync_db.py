"""라즈베리파이 로컬 DB <-> AWS RDS 양방향 동기화 스크립트.

주기적으로 실행하여 두 DB의 데이터를 updated_at 기준으로 동기화합니다.
연결 정보는 .env(SYNC_RASPBERRY_*, SYNC_RDS_*)에서 읽습니다.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pymysql
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

RASPBERRY = dict(
    host=os.getenv("SYNC_RASPBERRY_HOST"),
    user=os.getenv("SYNC_RASPBERRY_USER"),
    password=os.getenv("SYNC_RASPBERRY_PASSWORD"),
    db=os.getenv("SYNC_RASPBERRY_DB", "ohapjijol"),
    charset="utf8mb4",
)
RDS = dict(
    host=os.getenv("SYNC_RDS_HOST"),
    user=os.getenv("SYNC_RDS_USER"),
    password=os.getenv("SYNC_RDS_PASSWORD"),
    db=os.getenv("SYNC_RDS_DB", "ohapjijol"),
    charset="utf8mb4",
)

TABLES = {
    "user": "id",
    "project": "id",
    "task": "id",
    "todo": "id",
}


def _require_config(config: dict, label: str):
    missing = [k for k, v in config.items() if k != "charset" and not v]
    if missing:
        sys.exit(f"[설정 오류] {label} 환경변수 누락: {missing} — .env(SYNC_RASPBERRY_*, SYNC_RDS_*)를 확인하세요.")


def sync_table(table, pk_col):
    try:
        conn_a = pymysql.connect(**RASPBERRY, connect_timeout=3, cursorclass=pymysql.cursors.DictCursor)
        conn_b = pymysql.connect(**RDS, connect_timeout=3, cursorclass=pymysql.cursors.DictCursor)
    except Exception as e:
        print(f"[동기화 실패] DB 연결 오류: {e}")
        return

    with conn_a.cursor() as cur_a, conn_b.cursor() as cur_b:
        cur_a.execute(f"SELECT * FROM {table}")
        rows_a = {row[pk_col]: row for row in cur_a.fetchall()}

        cur_b.execute(f"SELECT * FROM {table}")
        rows_b = {row[pk_col]: row for row in cur_b.fetchall()}

        all_ids = set(rows_a.keys()) | set(rows_b.keys())

        for row_id in all_ids:
            row_a = rows_a.get(row_id)
            row_b = rows_b.get(row_id)

            if row_a and not row_b:
                insert_row(cur_b, table, row_a)
                print(f"[{table}] id={row_id} -> RDS에 새로 추가")
            elif row_b and not row_a:
                insert_row(cur_a, table, row_b)
                print(f"[{table}] id={row_id} -> 라즈베리파이에 새로 추가")
            elif row_a and row_b:
                ua = row_a.get("updated_at")
                ub = row_b.get("updated_at")
                # RDS(ub)는 UTC 기준이라 한국시간(+9시간)으로 보정해서 비교
                ub_corrected = ub + timedelta(hours=9) if ub else ub
                if ua and ub_corrected:
                    if ua > ub_corrected:
                        update_row(cur_b, table, pk_col, row_a)
                        print(f"[{table}] id={row_id} -> RDS를 라즈베리파이 데이터로 업데이트 (더 최신)")
                    elif ub_corrected > ua:
                        update_row(cur_a, table, pk_col, row_b)
                        print(f"[{table}] id={row_id} -> 라즈베리파이를 RDS 데이터로 업데이트 (더 최신)")

    conn_a.commit()
    conn_b.commit()
    conn_a.close()
    conn_b.close()


def insert_row(cursor, table, row):
    cols = ", ".join(row.keys())
    placeholders = ", ".join(["%s"] * len(row))
    sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
    cursor.execute(sql, list(row.values()))


def update_row(cursor, table, pk_col, row):
    set_clause = ", ".join([f"{k}=%s" for k in row.keys() if k != pk_col])
    values = [v for k, v in row.items() if k != pk_col]
    values.append(row[pk_col])
    sql = f"UPDATE {table} SET {set_clause} WHERE {pk_col}=%s"
    cursor.execute(sql, values)


if __name__ == "__main__":
    _require_config(RASPBERRY, "SYNC_RASPBERRY")
    _require_config(RDS, "SYNC_RDS")
    print(f"=== 동기화 시작: {datetime.now()} ===")
    for table, pk_col in TABLES.items():
        sync_table(table, pk_col)
    print(f"=== 동기화 완료: {datetime.now()} ===")
