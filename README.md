# 오합지졸.io 백엔드

`wrd.md`(요구사항 명세 및 개발 명세 v1.1) 기반 FastAPI 백엔드. REST API + 협업 **WebSocket hub** + `GET /health`.

유저 FE: [frontend_with](https://github.com/axMiniPrj4/frontend_with) · 관리자 FE: [new_frontAdmin](https://github.com/axMiniPrj4/new_frontAdmin)  
당일(프론트) 상세 대화록: 유저 FE 저장소의 `ai_talk.md` §12.

## 기술 스택

Python 3.12 · FastAPI · SQLAlchemy 2.0 / Alembic · MySQL 8 · Redis(Refresh Token) · JWT(Access 30분/Refresh 7일) · Pydantic v2 · (선택) OpenAI · 협업 WS(in-memory hub)

## 2026-07-15 업데이트 (AI 대화·구현)

커밋 예: `267a99b` on `feature/bsk/26.07.15`.

### 협업 WebSocket hub
인메모리 hub가 프로젝트 단위로 peer를 묶고, REST 변경·클라 state를 broadcast합니다. JWT `token` + `client_id` 쿼리.

| Hub 모듈 | WS 경로 (요지) | 역할 |
|----------|----------------|------|
| `workspace_hub` | `/api/projects/{id}/workspace/.../ws` | 코드 편집 중 라이브 sync |
| `whiteboard_hub` | `.../whiteboard/ws` | 보드 state / PUT 직후 broadcast |
| `chat_hub` | `.../chat/ws` | 메시지 POST 시 즉시 push |
| `erd_hub` | `.../erd/ws` | `erd-state` + PUT + optimistic lock |
| `video_hub` | `.../video/ws` | WebRTC 시그널링 · `GET .../video/live-peers` |

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
- `app/db/session.py`: 서버 **기동 시점**에 1차 DB(`DATABASE_URL`) 연결을 먼저 시도(3초 타임아웃) → 실패하면 RDS로 자동 전환 → 둘 다 실패하면 기동 실패(기존과 동일)
- 확인용 커넥션은 확인 직후 `dispose()`하여 SQLite 테스트 환경에서 파일 잠금이 남지 않도록 처리

**알려진 한계 (추가 작업 필요):**
- **부팅 시 1회 판단**만 함 — 운영 중 1차 DB가 죽어도 재시작 전엔 자동으로 안 넘어가고, RDS로 넘어간 뒤 1차 DB가 복구돼도 자동으로 되돌아오지 않음
- 1차 DB ↔ RDS 간 **실시간 복제/동기화 없음** — RDS는 특정 시점 스냅샷일 뿐이라, failover 시 그 이후 데이터는 유실됨
- RDS는 반드시 `alembic upgrade head`로 스키마를 최신까지 맞춰둬야 함 (2026-07-15 기준 1회 실행 완료 — 이후 새 마이그레이션 추가 시 RDS에도 별도로 적용 필요)

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
