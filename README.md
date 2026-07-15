# 오합지졸.io 백엔드

`wrd.md`(요구사항 명세 및 개발 명세 v1.1) 기반 FastAPI 백엔드. REST API + 협업 **WebSocket hub** + `GET /health`.

유저 FE: [frontend_with](https://github.com/axMiniPrj4/frontend_with) · 관리자 FE: [new_frontAdmin](https://github.com/axMiniPrj4/new_frontAdmin)  
당일(프론트) 상세 대화록: 유저 FE 저장소의 `ai_talk.md` §12.

## 기술 스택

Python 3.12 · FastAPI · SQLAlchemy 2.0 / Alembic · MySQL 8 · Redis(Refresh Token) · JWT(Access 30분/Refresh 7일) · Pydantic v2 · (선택) OpenAI · 협업 WS(in-memory hub)

## 2026-07-16 업데이트 — 협업 루프·Task·자료실·런타임 RDS

브랜치 `feature/bsk/26.07.15` 기준.

| 영역 | 내용 |
|------|------|
| 알림 | `notification` 테이블 + `/api/notifications*` , Task 담당/상태/댓글 훅 |
| My Work / 검색 | `GET /api/users/me/tasks`, `GET /api/search` |
| Task | `priority`, DONE 담당자 필수, `task_history`, 투두→Task `promote` |
| 투두 | priority·설명·기간·color·`IN_PROGRESS` |
| 자료실 | `project_id` 수정, 허용 확장자·50MB 확대 (`app/core/files.py`) |
| DB 페일오버 | **부팅 + 런타임** Pi 장애 시 `RDS_DATABASE_URL`로 엔진 교체 (`app/db/session.py`) |

마이그레이션: `a1b2c3d4e5f6`(notification), `b2c3d4e5f6a7`(priority·todo·history) — 운영 DB(Pi/RDS) 모두 `alembic upgrade head` 필요.

## 2026-07-15 업데이트 (AI 대화·구현)

커밋 예: `267a99b` on `feature/bsk/26.07.15`.

### 협업 WebSocket hub
인메모리 hub가 프로젝트 단위로 peer를 묶고, REST 변경·클라 state를 broadcast합니다. JWT `token` + `client_id` 쿼리.

| Hub 모듈 | WS 경로 (요지) | 역할 |
|----------|----------------|------|
| `workspace_hub` | `/api/projects/{id}/workspace/.../ws` | 코드 편집 중 라이브 sync + presence |
| `whiteboard_hub` | `.../whiteboard/ws` | 보드 state / PUT 직후 broadcast + optimistic lock(2026-07-15) |
| `chat_hub` | `.../chat/ws` | 메시지 POST 시 즉시 push + presence·typing(2026-07-15) |
| `erd_hub` | `.../erd/ws` | `erd-state` + PUT + optimistic lock |
| `video_hub` | `.../video/ws` | WebRTC 시그널링 · `GET .../video/live-peers` · presence에 `sharingScreen`(2026-07-15) |

FE는 Vite `/api` 프록시 `ws: true`로 접속합니다 (로컬에서 uvicorn 포트와 FE `vite.config` 일치 필요, 예: **8001**).

### AI 어시스턴트
키는 **백엔드 `.env`만** (프론트에 두지 않음):

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

미설정 시 가응답. 설정 후 서버 재시작.

### 관리자·결제 (당일 포함 확장)
- Admin API 확장, answer template, audit log, payment 모델/마이그레이션
- 시드: `python -m scripts.seed_admin` (+ `.env`의 `ADMIN_*` 기본값 가능)

### 인프라 검증 대시보드 (계획만)
유저 FE 숨김 페이지와 연동할 **ALB/ASG/CloudWatch + 실부하** API는 아직 없음.  
구현 시 사용자가 줄 값: `AWS_REGION`, ASG 이름, Target Group ARN, ALB 이름, 부하 URL, IAM Role 또는 Access Key.  
부하는 **ALB URL**로, 트래픽은 HTTP 러너 / CPU는 스케일 정책에 맞게 무거운 엔드포인트가 필요할 수 있음.  
구성은 **EC2 2대**(스케일 대상 타겟 + 부하 전용 러너, 러너는 타겟과 분리)로 검증 예정.

## 2026-07-15 추가 업데이트 — 1차 DB(라즈베리파이) 장애 대응

운영 중 라즈베리파이 DB가 일시적으로 응답하지 않는 상황을 겪고, 2차 DB(RDS)로 우회하는 안전망을 추가했습니다. (commit `59f7da5` on `feature/bsk/26.07.15`)

- `app/core/config.py`: `RDS_DATABASE_URL` 설정 추가 (미설정 시 우회 없이 기존과 동일)
- `app/db/session.py`:
  - **부팅:** 1차 DB(`DATABASE_URL`) 3초 타임아웃 연결 시도 → 실패 시 RDS
  - **런타임(2026-07-16):** `get_db()`에서 연결 장애 감지 시 RDS로 엔진·`SessionLocal` 교체 (재시작 없이 전환)
- `pool_pre_ping` + `connect_timeout=3`으로 불필요한 hang 완화

**알려진 한계:**
- RDS로 넘어간 뒤 1차 DB가 복구돼도 **자동 failback 없음** (재시작 또는 수동 전환)
- 1차 DB ↔ RDS 간 **실시간 복제/동기화 없음** — failover 시 스냅샷 차이로 데이터 공백 가능
- RDS는 `alembic upgrade head`로 스키마를 맞춰둬야 함
- WebSocket 경로의 `SessionLocal()` 직접 사용은 다음 연결부터 새 엔진을 탐 (진행 중 소켓은 제한적)

## 2026-07-15 추가 업데이트 — 공동작업 권한 레벨(뷰어/에디터)

`project_member.collab_permission`(`EDITOR` | `VIEWER`, 마이그레이션 `f7a8b9c0d1e2`) 추가. 팀 역할(LEADER/MEMBER)과는 별개 축으로, 팀장은 항상 편집 가능합니다.

- `app/core/deps.py`: `ProjectContext.is_editor` + `require_editor` 의존성 신규 (`require_leader`와 동일한 패턴)
- 적용 대상: 채팅 메시지 작성, 화이트보드 PUT/reset, ERD PUT, 워크스페이스 파일 생성/수정/삭제/복원 — REST뿐 아니라 WS 실시간 메시지(`board-state`/`erd-state`/`content-change`)도 뷰어면 서버에서 조용히 drop
- `PATCH /api/projects/{id}/members/{user_id}/permission` (팀장 전용) — 멤버 권한 변경

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

# 6) 서버 기동 (유저 FE vite 프록시가 8001이면 포트 맞춤)
.venv/bin/uvicorn app.main:app --reload --port 8001
```

Swagger: http://localhost:8001/docs

`REDIS_URL`을 비우면 인메모리 토큰 저장소로 폴백합니다(개발 전용 — 재기동 시 RT 소실).  
협업 WS hub는 프로세스 메모리 기준이라 **멀티 워커/멀티 인스턴스**에서는 공유되지 않습니다(단일 uvicorn 개발·소규모 배포 전제).

## 테스트

```bash
.venv/bin/pytest tests/ -q
```

SQLite + 인메모리 토큰 저장소로 전 도메인 통합 플로우(회원→프로젝트→업무→자료실→문의→관리자→위임/탈퇴/cascade 삭제)를 검증합니다.

## 프로젝트 구조

```
app/
  main.py
  core/              # config, errors, security(JWT), token_store, deps, …
  db/
  models/            # user, project, task, … + collaboration / payment / admin_audit 등
  schemas/
  routers/           # auth, users, projects, …, chat, whiteboard, erd, video, workspace, ai, admin
  services/
    chat_hub.py / erd_hub.py / whiteboard_hub.py / video_hub.py / workspace_hub.py
    openai_chat.py / payment_service.py / admin_audit.py / …
alembic/
scripts/seed_admin.py
tests/
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
