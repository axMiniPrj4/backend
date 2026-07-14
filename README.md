# 오합지졸.io 백엔드

`wrd.md`(요구사항 명세 및 개발 명세 v1.1) 기반 FastAPI 백엔드. API 54개 + `GET /health`.

## 기술 스택

Python 3.12 · FastAPI · SQLAlchemy 2.0 / Alembic · MySQL 8 · Redis(Refresh Token) · JWT(Access 30분/Refresh 7일) · Pydantic v2

## 실행 방법

```bash
# 1) 의존성 설치
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
#    (또는: uv venv .venv && uv pip install -p .venv/bin/python -r requirements.txt)

# 2) MySQL 8 + Redis 준비 (직접 설치, Docker 미사용)
#    Ubuntu 예시: sudo apt install mysql-server redis-server
sudo mysql -e "CREATE DATABASE ohapjijol CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'ohap'@'localhost' IDENTIFIED BY 'ohap';
GRANT ALL PRIVILEGES ON ohapjijol.* TO 'ohap'@'localhost';"

# 3) 환경 변수
cp .env.example .env   # 필요 시 수정 (운영에서는 JWT_SECRET_KEY 반드시 교체)

# 4) 마이그레이션
.venv/bin/alembic upgrade head

# 5) 초기 SYSTEM_ADMIN 시드 (가입 API로 생성 불가)
.venv/bin/python -m scripts.seed_admin <login_id> <password> <email>

# 6) 서버 기동
.venv/bin/uvicorn app.main:app --reload
```

Swagger: http://localhost:8000/docs

`REDIS_URL`을 비우면 인메모리 토큰 저장소로 폴백합니다(개발 전용 — 재기동 시 RT 소실).

## 테스트

```bash
.venv/bin/pytest tests/ -q
```

SQLite + 인메모리 토큰 저장소로 전 도메인 통합 플로우(회원→프로젝트→업무→자료실→문의→관리자→위임/탈퇴/cascade 삭제)를 검증합니다.

## 프로젝트 구조

```
app/
  main.py            # 앱 조립: CORS, 요청 로깅, /health, 라우터 9개
  core/
    config.py        # .env 기반 설정
    errors.py        # 에러 코드 상수 + AppError (단일 에러 포맷 {code, message, detail})
    handlers.py      # 전역 예외 핸들러
    security.py      # bcrypt / JWT 발급·검증
    token_store.py   # Refresh Token 저장소 (Redis, TTL=RT 만료 / 인메모리 폴백)
    deps.py          # 권한 체크 4단계 Depends 체인 (JWT→역할→멤버십→소유권)
    pagination.py    # page/size/sort 공통 (size≤100, 허용 외 정렬 400)
    files.py         # 파일 검증(20MB·확장자·MIME)·UUID 저장명·경로 조작 방지·스트리밍 다운로드
  db/
    base.py          # Base + TimestampMixin + SoftDeleteMixin(deleted_at IS NULL 자동 필터)
    session.py
  models/            # user, project(+member), task, todo, doc(+version), inquiry(+answer)
  schemas/           # XxxCreateRequest / XxxUpdateRequest / XxxResponse
  routers/           # auth, users, projects, members, tasks(gantt 포함), todos, docs(versions 포함), inquiries, admin
  services/          # 도메인 공유 로직 (회원 탈퇴, 프로젝트 cascade 삭제, 코드 발급)
alembic/             # 마이그레이션 (초기 스키마 v1.1)
scripts/seed_admin.py
tests/               # 통합 스모크 테스트 (15 케이스)
```

## 명세 대비 구현 메모

- **Soft Delete**: 세션 이벤트(`with_loader_criteria`)로 조회 시 `deleted_at IS NULL` 자동 적용.
  우회가 필요한 곳(중복 확인, 버전 MAX 계산)은 `execution_options(include_deleted=True)` 사용.
  `project_member`만 Hard Delete.
- **트랜잭션**: 프로젝트 생성(+코드+LEADER), 팀장 위임(교체), cascade 삭제, 자료 등록(doc+v1, 실패 시 물리 파일 롤백), 답변 등록(+상태 전환), 회원 탈퇴(3종 변형+RT 삭제) 모두 단일 커밋.
- **요금제**: PRO 전환 = 시점+30일, 재호출 = 만료 갱신, FREE = 즉시 해지. 만료는 로그인·/users/me 시점 lazy 전환(기준안 #8·#9).
- **탈퇴 변형**: `del_{UTC타임스탬프}_{원본}` → 동일 값 재가입 가능.

## 추가 기준안 (wrd.md에 없어 임의 확정 — 팀 승인 필요)

wrd.md 규칙 1(추측 금지)에 따라, schema.sql v1.1 미제공으로 아래 항목은 기준안으로 확정했습니다.

| 항목 | 기준안 |
| --- | --- |
| project.status 코드값 | `PLANNED \| IN_PROGRESS \| COMPLETED` (기본 PLANNED) |
| project.priority 코드값 | `LOW \| MEDIUM \| HIGH` (기본 MEDIUM) |
| 프로젝트 필드 | name(필수)·description·start_date·end_date(선택) |
| 참여 코드 형식 | 대문자+숫자 8자 (`secrets` 기반) |
| Todo 필드 | content(≤200자) + status |
| 중복 확인 응답 | `{"available": true/false}` (200) |
| 목록 응답 포맷 | `{items, page, size, total_elements, total_pages}` |
| 강퇴 시 본인 지정 | 400 (탈퇴/위임 사용 안내) |
| 문의 첨부 교체 | 미지원 (PATCH는 title/content만) |
| refresh 응답 | 새 AT + 기존 RT 에코 (미회전) |
