"""로컬 MariaDB 초기화 — root 비밀번호는 환경변수 LOCAL_MYSQL_ROOT_PASSWORD 사용."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def load_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def main() -> int:
    env = load_env(ENV_PATH)
    root_password = os.environ.get("LOCAL_MYSQL_ROOT_PASSWORD") or env.get("LOCAL_MYSQL_ROOT_PASSWORD")
    if not root_password:
        print("LOCAL_MYSQL_ROOT_PASSWORD 가 .env 또는 환경변수에 필요합니다.", file=sys.stderr)
        return 1

    db_name = env.get("MARIADB_DATABASE", "ohapjijol")
    db_user = env.get("MARIADB_USER", "ohap")
    db_password = env.get("MARIADB_PASSWORD", "dkagh1234")

    conn = pymysql.connect(
        host="localhost",
        user="root",
        password=root_password,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cur.execute(
                f"CREATE USER IF NOT EXISTS %s@'localhost' IDENTIFIED BY %s",
                (db_user, db_password),
            )
            cur.execute(f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO %s@'localhost'", (db_user,))
            cur.execute("FLUSH PRIVILEGES")
        print(f"OK: database `{db_name}` and user `{db_user}`@localhost")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
