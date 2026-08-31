"""전체 도메인 통합 스모크 테스트 — 정의 순서대로 실행되며 상태를 공유한다."""
import io

S = {}  # 테스트 간 공유 상태 (토큰, id 등)

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100  # 더미 파일 내용


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _signup(client, login_id, nickname, email, **overrides):
    payload = {
        "login_id": login_id, "password": "password1!", "name": "홍길동",
        "nickname": nickname, "email": email,
        "legal_agreed": True,
    }
    payload.update(overrides)
    return client.post("/api/auth/signup", json=payload)


def _login(client, login_id, password="password1!"):
    return client.post("/api/auth/login", json={"login_id": login_id, "password": password})


# ---------- Health / Auth ----------

def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_signup_and_duplicates(client):
    avatar_keys = []
    r = _signup(client, "leader1", "리더", "leader@test.io")
    assert r.status_code == 201, r.text
    assert r.json()["plan"] == "FREE"
    avatar_keys.append(r.json()["avatar_key"])
    assert avatar_keys[-1]

    r2 = _signup(client, "member2", "멤버", "member@test.io")
    assert r2.status_code == 201
    avatar_keys.append(r2.json()["avatar_key"])

    r3 = _signup(client, "other3", "아웃사이더", "other@test.io")
    assert r3.status_code == 201
    avatar_keys.append(r3.json()["avatar_key"])
    assert len(set(avatar_keys)) == 3

    assert _signup(client, "leader1", "다른닉", "x@test.io").json()["code"] == "DUPLICATE_LOGIN_ID"
    assert _signup(client, "newid99", "리더", "x@test.io").json()["code"] == "DUPLICATE_NICKNAME"
    assert _signup(client, "newid99", "다른닉", "leader@test.io").json()["code"] == "DUPLICATE_EMAIL"

    # 필수 동의: 이용약관·개인정보 처리방침(단일 체크박스) — 미동의면 400
    r = _signup(client, "agree99", "동의테스트", "agree@test.io", legal_agreed=False)
    assert r.status_code == 400 and r.json()["code"] == "VALIDATION_ERROR"

    # 비밀번호 정책: 8~16자, 영문+숫자+특수문자
    for bad in ("short1!", "password12", "verylongpassword1!"):  # 길이 미달 / 특수문자 없음 / 길이 초과
        r = client.post("/api/auth/signup", json={
            "login_id": "badpw123", "password": bad, "name": "n", "nickname": "badpw", "email": "badpw@test.io",
            "legal_agreed": True,
        })
        assert r.status_code == 400 and r.json()["code"] == "VALIDATION_ERROR", bad


def test_check_availability(client):
    assert client.get("/api/auth/check-login-id", params={"login_id": "leader1"}).json() == {"available": False}
    assert client.get("/api/auth/check-login-id", params={"login_id": "fresh_id"}).json() == {"available": True}
    assert client.get("/api/auth/check-email", params={"email": "leader@test.io"}).json() == {"available": False}
    assert client.get("/api/auth/check-nickname", params={"nickname": "리더"}).json() == {"available": False}


def test_login_and_refresh(client):
    assert _login(client, "leader1", "wrongpw99").status_code == 401
    assert _login(client, "no_such_user").status_code == 401  # 존재 여부 비노출: 동일 401

    for key, lid in (("leader", "leader1"), ("member", "member2"), ("other", "other3")):
        body = _login(client, lid).json()
        S[f"{key}_at"], S[f"{key}_rt"] = body["access_token"], body["refresh_token"]

    r = client.post("/api/auth/refresh", json={"refresh_token": S["leader_rt"]})
    assert r.status_code == 200 and r.json()["access_token"]

    # 로그아웃하면 RT 무효
    assert client.post("/api/auth/logout", headers=_auth(S["leader_at"])).status_code == 204
    assert client.post("/api/auth/refresh", json={"refresh_token": S["leader_rt"]}).status_code == 401
    S["leader_at"] = _login(client, "leader1").json()["access_token"]


# ---------- User ----------

def test_users_me(client):
    r = client.get("/api/users/me", headers=_auth(S["leader_at"]))
    assert r.status_code == 200 and r.json()["login_id"] == "leader1"
    assert client.get("/api/users/me").status_code == 401

    r = client.patch("/api/users/me", json={"nickname": "멤버"}, headers=_auth(S["leader_at"]))
    assert r.status_code == 409 and r.json()["code"] == "DUPLICATE_NICKNAME"
    r = client.patch("/api/users/me", json={"nickname": "리더킹"}, headers=_auth(S["leader_at"]))
    assert r.status_code == 200 and r.json()["nickname"] == "리더킹"


def test_change_password(client):
    # 전용 계정 사용 — 공유 상태(leader1 등)의 비밀번호를 건드리지 않는다
    assert _signup(client, "pwuser1", "비번유저", "pw@test.io").status_code == 201
    tokens = _login(client, "pwuser1").json()
    h = _auth(tokens["access_token"])

    r = client.post("/api/users/me/password", json={"current_password": "wrong1!", "new_password": "newpass2@"}, headers=h)
    assert r.status_code == 400 and r.json()["code"] == "INVALID_CREDENTIALS"
    r = client.post("/api/users/me/password", json={"current_password": "password1!", "new_password": "weak"}, headers=h)
    assert r.status_code == 400 and r.json()["code"] == "VALIDATION_ERROR"
    r = client.post("/api/users/me/password", json={"current_password": "password1!", "new_password": "password1!"}, headers=h)
    assert r.status_code == 400 and r.json()["code"] == "VALIDATION_ERROR"

    r = client.post("/api/users/me/password", json={"current_password": "password1!", "new_password": "newpass2@"}, headers=h)
    assert r.status_code == 204
    # 변경 후: 기존 비밀번호 로그인 불가, 새 비밀번호 로그인 가능, 기존 RT 폐기
    assert _login(client, "pwuser1").status_code == 401
    assert _login(client, "pwuser1", "newpass2@").status_code == 200
    r = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401


def test_login_history(client):
    # pwuser1의 누적 이력 (test_change_password에서): 성공 → 실패(변경 전 비밀번호) → 성공(새 비밀번호)
    at = _login(client, "pwuser1", "newpass2@").json()["access_token"]  # 성공 +1 → 총 4건
    r = client.get("/api/users/me/login-history", headers=_auth(at))
    assert r.status_code == 200
    body = r.json()
    assert body["total_elements"] == 4
    assert [i["success"] for i in body["items"]] == [True, True, False, True]  # 최신순
    assert body["items"][0]["ip"] and body["items"][0]["created_at"]

    r = client.get("/api/users/me/login-history", params={"page": 2, "size": 3}, headers=_auth(at))
    assert len(r.json()["items"]) == 1 and r.json()["total_pages"] == 2
    r = client.get("/api/users/me/login-history", params={"size": 0}, headers=_auth(at))
    assert r.status_code == 400


def test_plan_switch(client):
    r = client.put("/api/users/me/plan", json={"plan": "BASIC"}, headers=_auth(S["leader_at"]))
    assert r.status_code == 400 and r.json()["code"] == "INVALID_PLAN"
    r = client.put("/api/users/me/plan", json={"plan": "PRO"}, headers=_auth(S["leader_at"]))
    assert r.status_code == 200 and r.json()["plan"] == "PRO" and r.json()["plan_expires_at"]
    r = client.put("/api/users/me/plan", json={"plan": "FREE"}, headers=_auth(S["leader_at"]))
    assert r.status_code == 200 and r.json()["plan_expires_at"] is None


# ---------- Project / Member ----------

def test_project_create_join(client):
    r = client.post("/api/projects", json={"name": "부트캠프 프로젝트"}, headers=_auth(S["leader_at"]))
    assert r.status_code == 201, r.text
    S["pid"], S["code"] = r.json()["id"], r.json()["code"]

    r = client.post("/api/projects/join", json={"code": "WRONG123"}, headers=_auth(S["member_at"]))
    assert r.status_code == 404 and r.json()["code"] == "INVALID_PROJECT_CODE"
    assert client.post("/api/projects/join", json={"code": S["code"]}, headers=_auth(S["member_at"])).status_code == 201
    r = client.post("/api/projects/join", json={"code": S["code"]}, headers=_auth(S["member_at"]))
    assert r.status_code == 409 and r.json()["code"] == "ALREADY_JOINED"

    # 비멤버는 상세 403, 멤버는 200
    assert client.get(f"/api/projects/{S['pid']}", headers=_auth(S["other_at"])).status_code == 403
    assert client.get(f"/api/projects/{S['pid']}", headers=_auth(S["member_at"])).status_code == 200
    assert client.get("/api/projects/99999", headers=_auth(S["leader_at"])).status_code == 404

    r = client.get("/api/projects", headers=_auth(S["member_at"]))
    assert r.status_code == 200 and r.json()["total_elements"] == 1
    assert client.get("/api/projects", params={"sort": "hack,desc"}, headers=_auth(S["leader_at"])).status_code == 400

    # 수정/코드 재발급은 LEADER만
    assert client.patch(f"/api/projects/{S['pid']}", json={"status": "IN_PROGRESS"}, headers=_auth(S["member_at"])).status_code == 403
    assert client.patch(f"/api/projects/{S['pid']}", json={"status": "IN_PROGRESS"}, headers=_auth(S["leader_at"])).status_code == 200
    r = client.post(f"/api/projects/{S['pid']}/code", headers=_auth(S["leader_at"]))
    assert r.status_code == 200 and r.json()["code"] != S["code"]
    S["code"] = r.json()["code"]


def test_members(client):
    r = client.get(f"/api/projects/{S['pid']}/members", headers=_auth(S["member_at"]))
    assert r.status_code == 200 and len(r.json()) == 2
    S["leader_id"] = next(m["user_id"] for m in r.json() if m["role"] == "LEADER")
    S["member_id"] = next(m["user_id"] for m in r.json() if m["role"] == "MEMBER")

    # LEADER 탈퇴는 409, 강퇴는 LEADER만
    r = client.delete(f"/api/projects/{S['pid']}/members/me", headers=_auth(S["leader_at"]))
    assert r.status_code == 409 and r.json()["code"] == "LEADER_CANNOT_LEAVE"
    assert client.delete(f"/api/projects/{S['pid']}/members/{S['leader_id']}", headers=_auth(S["member_at"])).status_code == 403


# ---------- Task / Gantt ----------

def test_tasks(client):
    url = f"/api/projects/{S['pid']}/tasks"
    # 날짜 역전 400
    r = client.post(url, json={"title": "t", "start_date": "2026-07-20", "end_date": "2026-07-10"}, headers=_auth(S["leader_at"]))
    assert r.status_code == 400 and r.json()["code"] == "INVALID_DATE_RANGE"

    # 담당자 미지정 → 생성자 자동 할당
    r = client.post(url, json={"title": "리더의 업무", "start_date": "2026-07-14", "end_date": "2026-07-20"}, headers=_auth(S["leader_at"]))
    assert r.status_code == 201 and [a["id"] for a in r.json()["assignees"]] == [S["leader_id"]]
    S["task_leader"] = r.json()["id"]

    # 다중 담당자 지정 (중복은 제거됨)
    r = client.post(
        url,
        json={"title": "공동 업무", "assignee_ids": [S["member_id"], S["leader_id"], S["member_id"]],
              "start_date": "2026-07-15", "end_date": "2026-07-25"},
        headers=_auth(S["leader_at"]),
    )
    assert r.status_code == 201
    assert sorted(a["id"] for a in r.json()["assignees"]) == sorted([S["member_id"], S["leader_id"]])
    S["task_member"] = r.json()["id"]

    # 비멤버 담당자 지정 400
    r = client.post(url, json={"title": "x", "assignee_ids": [9999], "start_date": "2026-07-15", "end_date": "2026-07-16"}, headers=_auth(S["leader_at"]))
    assert r.status_code == 400

    # 수정: 편집 권한이 있는 팀원이면 누구나 가능 (2026-08 정책 변경, 이전에는 작성자/LEADER만)
    assert client.patch(f"{url}/{S['task_member']}", json={"title": "변경"}, headers=_auth(S["member_at"])).status_code == 200
    r = client.patch(f"{url}/{S['task_member']}", json={"title": "변경됨", "assignee_ids": [S["member_id"]]}, headers=_auth(S["leader_at"]))
    assert r.status_code == 200 and [a["id"] for a in r.json()["assignees"]] == [S["member_id"]]
    # 담당자 비우기는 불가 (최소 1명)
    assert client.patch(f"{url}/{S['task_member']}", json={"assignee_ids": []}, headers=_auth(S["leader_at"])).status_code == 400

    # 상태 변경도 편집 권한 팀원이면 담당 여부와 무관하게 가능 (2026-08 정책 변경)
    assert client.patch(f"{url}/{S['task_leader']}/status", json={"status": "DONE"}, headers=_auth(S["member_at"])).status_code == 200
    assert client.patch(f"{url}/{S['task_member']}/status", json={"status": "DONE"}, headers=_auth(S["member_at"])).status_code == 200
    assert client.patch(f"{url}/{S['task_member']}/status", json={"status": "BAD"}, headers=_auth(S["member_at"])).status_code == 400

    r = client.get(url, params={"status": "DONE"}, headers=_auth(S["member_at"]))
    # 위에서 두 작업 모두 DONE 으로 바꿨다
    assert r.status_code == 200 and r.json()["total_elements"] == 2
    # 담당자 필터: member2가 담당인 업무만
    r = client.get(url, params={"assignee_id": S["member_id"]}, headers=_auth(S["member_at"]))
    assert r.status_code == 200 and r.json()["total_elements"] == 1


def test_gantt(client):
    r = client.get(f"/api/projects/{S['pid']}/gantt", headers=_auth(S["member_at"]))
    assert r.status_code == 200
    body = r.json()
    # test_tasks 에서 두 작업 모두 DONE 으로 바뀐다
    assert body["total_tasks"] == 2 and body["done_tasks"] == 2 and body["progress"] == 100.0
    assert body["tasks"][0]["assignees"][0]["nickname"]


def test_daily_opr_source_and_save(client):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    report_date = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    base = f"/api/projects/{S['pid']}/opr"

    # 프로젝트 멤버만 날짜별 원천 데이터를 조회할 수 있다.
    assert client.get(f"{base}/source/{report_date}", headers=_auth(S["other_at"])).status_code == 403
    source = client.get(f"{base}/source/{report_date}", headers=_auth(S["member_at"]))
    assert source.status_code == 200, source.text
    assert source.json()["report_date"] == report_date
    # 자동 채움을 없앴다 — 빈 초안으로 시작한다 (routers/opr.py: get_opr_source)
    assert source.json()["rows"] == []

    payload = {
        "status": "DRAFT",
        "rows": [
            {
                "section_type": "TODAY",
                "content": "OPR 화면 구현",
                "status": "진행 중",
                "assignee_name": "리더킹",
                "planned_date": report_date,
                "task_id": S["task_leader"],
                "source": "MANUAL",
                "sort_order": 0,
            },
            {
                "section_type": "ISSUE",
                "content": "검토 일정 확인",
                "status": "대응 중",
                "issue_request": "팀 검토 요청",
                "source": "MANUAL",
                "sort_order": 1,
            },
        ],
    }
    created = client.put(f"{base}/{report_date}", json=payload, headers=_auth(S["leader_at"]))
    assert created.status_code == 200, created.text
    report_id = created.json()["id"]
    S["leader_opr_id"] = report_id
    assert len(created.json()["rows"]) == 2

    # 개인 탭에서는 같은 날짜라도 다른 사람의 OPR이 보이지 않는다.
    assert client.get(f"{base}/{report_date}", headers=_auth(S["member_at"])).status_code == 404

    member_payload = {
        "status": "DRAFT",
        "rows": [
            {
                "section_type": "COMPLETED",
                "content": "공동 업무 완료",
                "status": "완료",
                "completed_date": report_date,
                "task_id": S["task_member"],
                "source": "AUTO",
                "sort_order": 0,
            }
        ],
    }
    member_created = client.put(
        f"{base}/{report_date}", json=member_payload, headers=_auth(S["member_at"])
    )
    assert member_created.status_code == 200, member_created.text
    member_report_id = member_created.json()["id"]
    S["member_opr_id"] = member_report_id
    assert member_report_id != report_id

    # 팀 탭에서는 같은 프로젝트·날짜의 개인 OPR을 작성자별로 함께 본다.
    team = client.get(f"{base}/team/{report_date}", headers=_auth(S["member_at"]))
    assert team.status_code == 200
    assert {report["id"] for report in team.json()} == {report_id, member_report_id}
    assert all(report["author_nickname"] for report in team.json())

    # 같은 작성자·프로젝트·날짜는 새 문서가 아니라 본인의 기존 OPR을 갱신한다.
    member_payload["status"] = "SHARED"
    updated = client.put(f"{base}/{report_date}", json=member_payload, headers=_auth(S["member_at"]))
    assert updated.status_code == 200
    assert updated.json()["id"] == member_report_id
    assert updated.json()["status"] == "SHARED" and len(updated.json()["rows"]) == 1


# ---------- Task 댓글 + 좋아요 ----------

def test_task_comments(client):
    url = f"/api/projects/{S['pid']}/tasks/{S['task_member']}/comments"
    # 비멤버 403, 없는 Task 404
    assert client.post(url, json={"content": "x"}, headers=_auth(S["other_at"])).status_code == 403
    assert client.get(f"/api/projects/{S['pid']}/tasks/99999/comments", headers=_auth(S["member_at"])).status_code == 404

    r = client.post(url, json={"content": "일정 확인 부탁해요"}, headers=_auth(S["member_at"]))
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["author_nickname"] and c["like_count"] == 0 and c["liked_by_me"] is False
    S["comment_id"] = c["id"]

    # 좋아요: 리더+본인 → 2, 멱등(재호출해도 2), 취소 → 1
    assert client.post(f"{url}/{c['id']}/like", headers=_auth(S["leader_at"])).json()["like_count"] == 1
    r = client.post(f"{url}/{c['id']}/like", headers=_auth(S["member_at"]))
    assert r.json()["like_count"] == 2 and r.json()["liked_by_me"] is True
    assert client.post(f"{url}/{c['id']}/like", headers=_auth(S["member_at"])).json()["like_count"] == 2
    r = client.delete(f"{url}/{c['id']}/like", headers=_auth(S["leader_at"]))
    assert r.json()["like_count"] == 1 and r.json()["liked_by_me"] is False

    # 목록 (작성순)
    client.post(url, json={"content": "확인했습니다"}, headers=_auth(S["leader_at"]))
    r = client.get(url, headers=_auth(S["member_at"]))
    assert r.status_code == 200 and len(r.json()) == 2 and r.json()[0]["id"] == S["comment_id"]

    # 삭제: 작성자 아닌 멤버 403 (리더 댓글을 member2가), 작성자 본인 204
    leader_comment_id = r.json()[1]["id"]
    assert client.delete(f"{url}/{leader_comment_id}", headers=_auth(S["member_at"])).status_code == 403
    assert client.delete(f"{url}/{S['comment_id']}", headers=_auth(S["member_at"])).status_code == 204
    assert len(client.get(url, headers=_auth(S["member_at"])).json()) == 1


# ---------- Todo ----------

def test_todos(client):
    r = client.post("/api/todos", json={"content": "회고 작성"}, headers=_auth(S["member_at"]))
    assert r.status_code == 201
    todo_id = r.json()["id"]
    # 타인의 Todo는 404 (존재 비노출)
    assert client.patch(f"/api/todos/{todo_id}", json={"status": "DONE"}, headers=_auth(S["leader_at"])).status_code == 404
    assert client.patch(f"/api/todos/{todo_id}", json={"status": "DONE"}, headers=_auth(S["member_at"])).status_code == 200
    r = client.get("/api/todos", params={"status": "DONE"}, headers=_auth(S["member_at"]))
    assert r.status_code == 200 and len(r.json()) == 1
    assert client.delete(f"/api/todos/{todo_id}", headers=_auth(S["member_at"])).status_code == 204
    assert client.get("/api/todos", headers=_auth(S["member_at"])).json() == []


# ---------- 프로젝트 할 일 ----------

def test_project_todos(client):
    url = f"/api/projects/{S['pid']}/todos"
    # 비멤버 403
    assert client.post(url, json={"content": "x"}, headers=_auth(S["other_at"])).status_code == 403

    r = client.post(url, json={"content": "회의록 정리", "priority": "HIGH"}, headers=_auth(S["member_at"]))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["priority"] == "HIGH" and body["status"] == "NOT_DONE" and body["author_nickname"]
    ptodo_id = body["id"]
    assert client.post(url, json={"content": "x", "priority": "BAD"}, headers=_auth(S["member_at"])).status_code == 400

    # 작성자 본인 완료 토글
    r = client.patch(f"{url}/{ptodo_id}", json={"status": "DONE"}, headers=_auth(S["member_at"]))
    assert r.status_code == 200 and r.json()["status"] == "DONE"
    # LEADER는 타인 작성분도 수정 가능
    assert client.patch(f"{url}/{ptodo_id}", json={"content": "회의록 정리(팀장 수정)"}, headers=_auth(S["leader_at"])).status_code == 200

    r = client.get(url, params={"status": "DONE"}, headers=_auth(S["leader_at"]))
    assert r.status_code == 200 and len(r.json()) == 1

    # 삭제 후 404
    assert client.delete(f"{url}/{ptodo_id}", headers=_auth(S["member_at"])).status_code == 204
    assert client.get(url, headers=_auth(S["member_at"])).json() == []


# ---------- Doc / DocVersion ----------

def test_docs_and_versions(client):
    url = f"/api/projects/{S['pid']}/docs"
    # 허용되지 않는 확장자 400
    r = client.post(url, data={"title": "문서"}, files={"file": ("evil.exe", io.BytesIO(PNG), "application/octet-stream")}, headers=_auth(S["leader_at"]))
    assert r.status_code == 400 and r.json()["code"] == "INVALID_FILE_TYPE"
    # 용량 초과 413 (테스트 환경 MAX 1KB)
    r = client.post(url, data={"title": "문서"}, files={"file": ("big.png", io.BytesIO(b"0" * 2048), "image/png")}, headers=_auth(S["leader_at"]))
    assert r.status_code == 413 and r.json()["code"] == "FILE_TOO_LARGE"

    # 등록 → v1 자동 생성
    r = client.post(url, data={"title": "설계 문서", "content": "초안"}, files={"file": ("design_v1.png", io.BytesIO(PNG), "image/png")}, headers=_auth(S["leader_at"]))
    assert r.status_code == 201, r.text
    S["doc_id"] = r.json()["id"]
    assert r.json()["latest_version"]["version_no"] == 1

    # 새 버전 업로드는 멤버 누구나
    r = client.post(f"{url}/{S['doc_id']}/versions", files={"file": ("design_v2.png", io.BytesIO(PNG + b"v2"), "image/png")}, headers=_auth(S["member_at"]))
    assert r.status_code == 201 and r.json()["version_no"] == 2

    # 최신 버전 다운로드 = v2 (원본 파일명 복원)
    r = client.get(f"{url}/{S['doc_id']}/file", headers=_auth(S["member_at"]))
    assert r.status_code == 200 and r.content == PNG + b"v2"
    assert "design_v2.png" in r.headers["content-disposition"]

    # 특정 버전 다운로드
    r = client.get(f"{url}/{S['doc_id']}/versions/1/file", headers=_auth(S["member_at"]))
    assert r.status_code == 200 and r.content == PNG

    # 게시글 수정은 작성자/LEADER만 (JSON)
    assert client.patch(f"{url}/{S['doc_id']}", json={"title": "수정"}, headers=_auth(S["member_at"])).status_code == 403
    assert client.patch(f"{url}/{S['doc_id']}", json={"title": "설계 문서 v2"}, headers=_auth(S["leader_at"])).status_code == 200

    # 버전 삭제: 업로더 본인(member) 가능 → 이후 최신은 v1
    assert client.delete(f"{url}/{S['doc_id']}/versions/2", headers=_auth(S["member_at"])).status_code == 204
    r = client.get(f"{url}/{S['doc_id']}", headers=_auth(S["member_at"]))
    assert r.json()["latest_version"]["version_no"] == 1
    # 마지막 버전 삭제 불가 409
    r = client.delete(f"{url}/{S['doc_id']}/versions/1", headers=_auth(S["leader_at"]))
    assert r.status_code == 409 and r.json()["code"] == "LAST_VERSION_CANNOT_DELETE"
    # 삭제된 버전 재삭제 → 404
    assert client.delete(f"{url}/{S['doc_id']}/versions/2", headers=_auth(S["member_at"])).status_code == 404

    # 목록
    r = client.get(url, headers=_auth(S["member_at"]))
    assert r.status_code == 200 and r.json()["total_elements"] == 1

    # 관계 API 테스트가 같은 자료를 사용한 뒤 정리한다.


def test_task_opr_doc_relations(client):
    pid = S["pid"]
    task_id = S["task_leader"]
    doc_id = S["doc_id"]
    report_id = S["leader_opr_id"]

    task_doc_url = f"/api/projects/{pid}/tasks/{task_id}/docs/{doc_id}"
    opr_doc_url = f"/api/projects/{pid}/opr/reports/{report_id}/docs/{doc_id}"

    # 비멤버는 관계 조회·연결 불가
    assert client.get(f"/api/projects/{pid}/tasks/{task_id}/relations", headers=_auth(S["other_at"])).status_code == 403

    # Task/OPR에 같은 자료를 연결하며, 중복 POST는 멱등이다.
    assert client.post(task_doc_url, headers=_auth(S["leader_at"])).status_code == 200
    assert client.post(task_doc_url, headers=_auth(S["leader_at"])).status_code == 200
    assert client.post(opr_doc_url, headers=_auth(S["leader_at"])).status_code == 200

    task_rel = client.get(
        f"/api/projects/{pid}/tasks/{task_id}/relations", headers=_auth(S["member_at"])
    )
    assert task_rel.status_code == 200, task_rel.text
    assert task_rel.json()["documents"][0]["id"] == doc_id
    assert any(report["report_id"] == report_id for report in task_rel.json()["opr_reports"])

    opr_rel = client.get(
        f"/api/projects/{pid}/opr/reports/{report_id}/relations", headers=_auth(S["member_at"])
    )
    assert opr_rel.status_code == 200
    assert {task["id"] for task in opr_rel.json()["tasks"]} == {task_id}
    assert opr_rel.json()["documents"][0]["id"] == doc_id

    doc_rel = client.get(
        f"/api/projects/{pid}/docs/{doc_id}/relations", headers=_auth(S["member_at"])
    )
    assert doc_rel.status_code == 200
    assert task_id in {task["id"] for task in doc_rel.json()["tasks"]}
    assert report_id in {report["report_id"] for report in doc_rel.json()["opr_reports"]}

    # 담당자가 아닌 멤버는 다른 사람의 Task 연결을 해제할 수 없다.
    assert client.delete(task_doc_url, headers=_auth(S["member_at"])).status_code == 403
    assert client.delete(opr_doc_url, headers=_auth(S["leader_at"])).status_code == 204
    assert client.delete(task_doc_url, headers=_auth(S["leader_at"])).status_code == 204

    # 관계 정리 후 기존 자료 삭제 정책도 유지된다.
    docs_url = f"/api/projects/{pid}/docs"
    assert client.delete(f"{docs_url}/{doc_id}", headers=_auth(S["leader_at"])).status_code == 204
    assert client.get(f"{docs_url}/{doc_id}", headers=_auth(S["member_at"])).status_code == 404


# ---------- 전역 자료실 (공통 자료 + 내 프로젝트 자료) ----------

# ---------- OPR AI 사용 기록 ----------

def _ai_payload(**overrides):
    payload = {
        "title": "로그인 오류 분석",
        "question": "JWT 갱신 오류 원인 분석",
        "answer_summary": "동시 요청에서 refresh 토큰이 두 번 소비됨",
        "application_result": "요청 잠금 적용 후 오류 해결",
        "lesson_learned": "토큰 갱신은 단일 비행으로 처리한다",
        "providers": [{"provider": "CHATGPT"}, {"provider": "CLAUDE"}],
        "task_ids": [S["task_leader"]],
        "doc_ids": [S["doc_id"]],
    }
    payload.update(overrides)
    return payload


def test_opr_ai_records_crud(client):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    # 다른 테스트 상태에 의존하지 않도록 이 테스트 전용 OPR 을 만든다
    day = (datetime.now(ZoneInfo("Asia/Seoul")).date() - timedelta(days=5)).isoformat()
    opr_base = f"/api/projects/{S['pid']}/opr"
    own = client.put(
        f"{opr_base}/{day}", json={"status": "DRAFT", "rows": []}, headers=_auth(S["leader_at"])
    )
    assert own.status_code == 200, own.text
    base = f"{opr_base}/reports/{own.json()['id']}/ai-records"

    # 생성 — AI 복수 선택 + WBS·자료 연결
    r = client.post(base, json=_ai_payload(), headers=_auth(S["leader_at"]))
    assert r.status_code == 201, r.text
    body = r.json()
    S["ai_record_id"] = body["id"]
    assert [p["provider"] for p in body["providers"]] == ["CHATGPT", "CLAUDE"]
    assert body["task_ids"] == [S["task_leader"]]
    assert body["doc_ids"] == [S["doc_id"]]
    assert body["author_id"] == S["leader_id"]

    # 조회 — 같은 프로젝트 팀원은 읽을 수 있고, 비멤버는 막힌다
    listed = client.get(base, headers=_auth(S["member_at"]))
    assert listed.status_code == 200 and len(listed.json()) == 1
    assert client.get(base, headers=_auth(S["other_at"])).status_code == 403

    # WBS·자료 없이도 저장된다
    r = client.post(
        base,
        json=_ai_payload(title="WBS 없는 기록", task_ids=[], doc_ids=[]),
        headers=_auth(S["leader_at"]),
    )
    assert r.status_code == 201, r.text
    assert r.json()["task_ids"] == [] and r.json()["doc_ids"] == []
    no_wbs_id = r.json()["id"]

    # 같은 AI 중복 차단
    assert client.post(
        base,
        json=_ai_payload(providers=[{"provider": "CHATGPT"}, {"provider": "CHATGPT"}]),
        headers=_auth(S["leader_at"]),
    ).status_code == 400

    # AI 최소 1개
    assert client.post(
        base, json=_ai_payload(providers=[]), headers=_auth(S["leader_at"])
    ).status_code == 400

    # 기타: 이름 없으면 400, 있으면 통과
    assert client.post(
        base, json=_ai_payload(providers=[{"provider": "OTHER"}]), headers=_auth(S["leader_at"])
    ).status_code == 400
    other_ok = client.post(
        base,
        json=_ai_payload(
            title="기타 AI",
            providers=[{"provider": "OTHER", "custom_provider_name": "사내 LLM"}],
        ),
        headers=_auth(S["leader_at"]),
    )
    assert other_ok.status_code == 201, other_ok.text
    assert other_ok.json()["providers"][0]["custom_provider_name"] == "사내 LLM"
    # 같은 '기타'라도 이름이 다르면 함께 넣을 수 있다
    two_others = client.post(
        base,
        json=_ai_payload(
            title="기타 둘",
            providers=[
                {"provider": "OTHER", "custom_provider_name": "사내 LLM"},
                {"provider": "OTHER", "custom_provider_name": "다른 LLM"},
            ],
        ),
        headers=_auth(S["leader_at"]),
    )
    assert two_others.status_code == 201, two_others.text
    two_others_id = two_others.json()["id"]

    # 알 수 없는 provider
    assert client.post(
        base, json=_ai_payload(providers=[{"provider": "UNKNOWN_AI"}]), headers=_auth(S["leader_at"])
    ).status_code == 400

    # 필수 문자열 공백 차단
    for field in ("title", "question", "application_result"):
        assert client.post(
            base, json=_ai_payload(**{field: "   "}), headers=_auth(S["leader_at"])
        ).status_code == 400, field

    # 길이 초과 차단
    assert client.post(
        base, json=_ai_payload(title="가" * 201), headers=_auth(S["leader_at"])
    ).status_code == 400

    # 접근할 수 없는 WBS·자료 연결 차단
    assert client.post(
        base, json=_ai_payload(task_ids=[999999]), headers=_auth(S["leader_at"])
    ).status_code == 400
    assert client.post(
        base, json=_ai_payload(doc_ids=[999999]), headers=_auth(S["leader_at"])
    ).status_code == 400

    # 남의 기록은 수정·삭제할 수 없다
    rid = S["ai_record_id"]
    assert client.patch(
        f"{base}/{rid}", json={"title": "가로채기"}, headers=_auth(S["member_at"])
    ).status_code == 403
    assert client.delete(f"{base}/{rid}", headers=_auth(S["member_at"])).status_code == 403

    # 수정 — 보낸 필드만 바뀐다
    patched = client.patch(
        f"{base}/{rid}",
        json={
            "title": "로그인 오류 분석 v2",
            "providers": [{"provider": "GEMINI"}],
            "task_ids": [],
        },
        headers=_auth(S["leader_at"]),
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["title"] == "로그인 오류 분석 v2"
    assert [p["provider"] for p in patched.json()["providers"]] == ["GEMINI"]
    assert patched.json()["task_ids"] == []
    assert patched.json()["question"] == "JWT 갱신 오류 원인 분석"  # 안 보낸 필드는 유지
    assert patched.json()["doc_ids"] == [S["doc_id"]]

    # 수정 시에도 검증은 동일
    assert client.patch(
        f"{base}/{rid}", json={"providers": []}, headers=_auth(S["leader_at"])
    ).status_code == 400

    # 삭제 — 해당 기록만 사라진다
    assert client.delete(f"{base}/{two_others_id}", headers=_auth(S["leader_at"])).status_code == 204
    assert client.delete(f"{base}/{no_wbs_id}", headers=_auth(S["leader_at"])).status_code == 204
    remaining = {item["id"] for item in client.get(base, headers=_auth(S["leader_at"])).json()}
    assert no_wbs_id not in remaining and two_others_id not in remaining and rid in remaining

    # 없는 기록 삭제는 404
    assert client.delete(f"{base}/{no_wbs_id}", headers=_auth(S["leader_at"])).status_code == 404

    # 이 테스트가 만든 OPR 은 정리한다 (다른 테스트 상태를 건드리지 않기 위함)
    assert client.delete(f"{opr_base}/{day}", headers=_auth(S["leader_at"])).status_code == 204


def test_opr_ai_records_via_report_save(client):
    """OPR 통째 저장(PUT)으로도 AI 기록을 다룬다.

    공유 상태를 건드리지 않도록 별도 날짜의 OPR·임시 작업으로 검증한다.
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    day = (datetime.now(ZoneInfo("Asia/Seoul")).date() - timedelta(days=3)).isoformat()
    base = f"/api/projects/{S['pid']}/opr"

    temp = client.post(
        f"/api/projects/{S['pid']}/tasks",
        json={
            "title": "AI 기록 연결용 임시 작업",
            "start_date": "2026-07-14",
            "end_date": "2026-07-20",
        },
        headers=_auth(S["leader_at"]),
    )
    assert temp.status_code == 201, temp.text
    temp_task_id = temp.json()["id"]

    saved = client.put(
        f"{base}/{day}",
        json={
            "status": "DRAFT",
            "rows": [],
            "ai_records": [
                {
                    "title": "저장으로 생성 1",
                    "question": "질문 1",
                    "application_result": "결과 1",
                    "providers": [{"provider": "COPILOT"}],
                    "task_ids": [temp_task_id],
                },
                {
                    "title": "저장으로 생성 2",
                    "question": "질문 2",
                    "application_result": "결과 2",
                    "providers": [{"provider": "PERPLEXITY"}],
                },
            ],
        },
        headers=_auth(S["leader_at"]),
    )
    assert saved.status_code == 200, saved.text
    report_id = saved.json()["id"]
    records = saved.json()["ai_records"]
    assert len(records) == 2
    assert [item["sort_order"] for item in records] == [0, 1]
    kept_id = records[0]["id"]
    ai_base = f"{base}/reports/{report_id}/ai-records"

    # ai_records 를 생략하면 기존 기록을 그대로 둔다 (구버전 클라이언트 호환)
    again = client.put(
        f"{base}/{day}", json={"status": "DRAFT", "rows": []}, headers=_auth(S["leader_at"])
    )
    assert again.status_code == 200, again.text
    assert len(again.json()["ai_records"]) == 2

    # 목록을 보내면 그 목록으로 맞춘다 — id 는 유지된 채 갱신되고, 빠진 기록은 삭제된다
    trimmed = client.put(
        f"{base}/{day}",
        json={
            "status": "DRAFT",
            "rows": [],
            "ai_records": [
                {
                    "id": kept_id,
                    "title": "갱신됨",
                    "question": "질문 1",
                    "application_result": "결과 1",
                    "providers": [{"provider": "GEMINI"}],
                }
            ],
        },
        headers=_auth(S["leader_at"]),
    )
    assert trimmed.status_code == 200, trimmed.text
    assert len(trimmed.json()["ai_records"]) == 1
    assert trimmed.json()["ai_records"][0]["id"] == kept_id
    assert trimmed.json()["ai_records"][0]["title"] == "갱신됨"

    # 남의 OPR 에는 AI 기록을 넣을 수 없다
    assert client.post(
        ai_base,
        json={
            "title": "침입",
            "question": "q",
            "application_result": "r",
            "providers": [{"provider": "CLAUDE"}],
        },
        headers=_auth(S["member_at"]),
    ).status_code == 403

    # WBS 를 삭제해도 AI 기록 자체는 남는다
    removed = client.delete(
        f"/api/projects/{S['pid']}/tasks/{temp_task_id}", headers=_auth(S["leader_at"])
    )
    assert removed.status_code in (200, 204), removed.text
    assert len(client.get(ai_base, headers=_auth(S["leader_at"])).json()) == 1

    # OPR 을 삭제하면 AI 기록도 함께 사라진다
    assert client.delete(f"{base}/{day}", headers=_auth(S["leader_at"])).status_code == 204
    assert client.get(ai_base, headers=_auth(S["leader_at"])).status_code == 404


def test_archive(client):
    # 프로젝트 자료 1건 생성 (멤버 전용 자료)
    r = client.post(
        f"/api/projects/{S['pid']}/docs",
        data={"title": "프로젝트 전용 문서"},
        files={"file": ("proj.png", io.BytesIO(PNG), "image/png")},
        headers=_auth(S["leader_at"]),
    )
    assert r.status_code == 201
    proj_doc_id = r.json()["id"]

    # 공통 자료 등록 — 로그인 사용자 누구나 (비멤버 other3도 가능)
    r = client.post(
        "/api/archive",
        data={"title": "전체 공지 템플릿", "content": "모두 사용"},
        files={"file": ("common.png", io.BytesIO(PNG), "image/png")},
        headers=_auth(S["other_at"]),
    )
    assert r.status_code == 201, r.text
    common = r.json()
    assert common["project_id"] is None and common["project_name"] is None
    assert common["latest_version"]["version_no"] == 1
    common_id = common["id"]

    # 전역 목록: 멤버는 공통+프로젝트 자료, 비멤버는 공통만
    r = client.get("/api/archive", headers=_auth(S["member_at"]))
    ids = [d["id"] for d in r.json()["items"]]
    assert common_id in ids and proj_doc_id in ids
    r = client.get("/api/archive", headers=_auth(S["other_at"]))
    ids = [d["id"] for d in r.json()["items"]]
    assert common_id in ids and proj_doc_id not in ids
    # 필터: 공통만 / 제목 검색
    assert client.get("/api/archive", params={"common_only": True}, headers=_auth(S["member_at"])).json()["total_elements"] == 1
    assert client.get("/api/archive", params={"q": "템플릿"}, headers=_auth(S["other_at"])).json()["total_elements"] == 1

    # 상세/다운로드 — 공통 자료는 누구나, 프로젝트 자료는 비멤버 403
    assert client.get(f"/api/archive/{common_id}/file", headers=_auth(S["member_at"])).status_code == 200
    assert client.get(f"/api/archive/{proj_doc_id}", headers=_auth(S["member_at"])).status_code == 200
    assert client.get(f"/api/archive/{proj_doc_id}", headers=_auth(S["other_at"])).status_code == 403

    # 공통 자료 수정/새 버전: 작성자(other3)만
    assert client.patch(f"/api/archive/{common_id}", json={"title": "x"}, headers=_auth(S["member_at"])).status_code == 403
    assert client.patch(f"/api/archive/{common_id}", json={"title": "전체 공지 템플릿 v2"}, headers=_auth(S["other_at"])).status_code == 200
    r = client.post(f"/api/archive/{common_id}/versions", files={"file": ("c2.png", io.BytesIO(PNG + b"2"), "image/png")}, headers=_auth(S["member_at"]))
    assert r.status_code == 403
    r = client.post(f"/api/archive/{common_id}/versions", files={"file": ("c2.png", io.BytesIO(PNG + b"2"), "image/png")}, headers=_auth(S["other_at"]))
    assert r.status_code == 201 and r.json()["version_no"] == 2
    assert len(client.get(f"/api/archive/{common_id}/versions", headers=_auth(S["member_at"])).json()) == 2

    # 프로젝트 자료도 전역 경로로 버전 업로드 가능 (멤버, 기존 정책)
    r = client.post(f"/api/archive/{proj_doc_id}/versions", files={"file": ("p2.png", io.BytesIO(PNG), "image/png")}, headers=_auth(S["member_at"]))
    assert r.status_code == 201

    # 삭제: 작성자만 → 이후 404, 목록에서 제외
    assert client.delete(f"/api/archive/{common_id}", headers=_auth(S["member_at"])).status_code == 403
    assert client.delete(f"/api/archive/{common_id}", headers=_auth(S["other_at"])).status_code == 204
    assert client.get(f"/api/archive/{common_id}", headers=_auth(S["other_at"])).status_code == 404
    assert client.get("/api/archive", headers=_auth(S["other_at"])).json()["total_elements"] == 0
    # 프로젝트 자료 정리 (이후 테스트 영향 방지)
    assert client.delete(f"/api/projects/{S['pid']}/docs/{proj_doc_id}", headers=_auth(S["leader_at"])).status_code == 204


# ---------- Inquiry / Answer / Admin ----------

def test_inquiries_and_admin(client):
    # 시드 스크립트로 SYSTEM_ADMIN 생성 (가입 API로 생성 불가)
    from scripts.seed_admin import main as seed_main
    import sys
    old = sys.argv
    sys.argv = ["seed_admin", "sysadmin", "admin1234", "admin@test.io"]
    seed_main()
    sys.argv = old
    S["admin_at"] = _login(client, "sysadmin", "admin1234").json()["access_token"]

    # 문의 등록 (첨부 포함, project_id 없음 = 일반 문의)
    r = client.post("/api/inquiries", data={"title": "로그인 문의", "content": "안 돼요"},
                    files={"file": ("shot.png", io.BytesIO(PNG), "image/png")}, headers=_auth(S["member_at"]))
    assert r.status_code == 201 and r.json()["status"] == "WAITING"
    S["q_id"] = r.json()["id"]

    # 본인 것만 조회 — 타인 403, ADMIN 200
    assert client.get(f"/api/inquiries/{S['q_id']}", headers=_auth(S["leader_at"])).status_code == 403
    assert client.get(f"/api/inquiries/{S['q_id']}", headers=_auth(S["admin_at"])).status_code == 200

    # WAITING 상태 수정 가능
    assert client.patch(f"/api/inquiries/{S['q_id']}", json={"title": "로그인 문의(수정)"}, headers=_auth(S["member_at"])).status_code == 200

    # 답변: ADMIN만, 등록 시 ANSWERED 전환
    assert client.post(f"/api/inquiries/{S['q_id']}/answer", json={"content": "답"}, headers=_auth(S["member_at"])).status_code == 403
    r = client.post(f"/api/inquiries/{S['q_id']}/answer", json={"content": "확인했습니다"}, headers=_auth(S["admin_at"]))
    assert r.status_code == 201
    assert client.get(f"/api/inquiries/{S['q_id']}", headers=_auth(S["member_at"])).json()["status"] == "ANSWERED"

    # 중복 답변 409 / 답변 완료 후 수정·삭제 409
    r = client.post(f"/api/inquiries/{S['q_id']}/answer", json={"content": "again"}, headers=_auth(S["admin_at"]))
    assert r.status_code == 409 and r.json()["code"] == "ANSWER_EXISTS"
    r = client.patch(f"/api/inquiries/{S['q_id']}", json={"title": "x"}, headers=_auth(S["member_at"]))
    assert r.status_code == 409 and r.json()["code"] == "ALREADY_ANSWERED"
    assert client.delete(f"/api/inquiries/{S['q_id']}", headers=_auth(S["member_at"])).status_code == 409

    # 관리자 목록 — 일반 유저 403
    assert client.get("/api/admin/users", headers=_auth(S["member_at"])).status_code == 403
    r = client.get("/api/admin/users", params={"keyword": "leader1"}, headers=_auth(S["admin_at"]))
    assert r.status_code == 200 and r.json()["total_elements"] == 1
    assert client.get("/api/admin/projects", headers=_auth(S["admin_at"])).json()["total_elements"] == 1
    r = client.get("/api/admin/inquiries", params={"status": "ANSWERED"}, headers=_auth(S["admin_at"]))
    assert r.status_code == 200 and r.json()["total_elements"] == 1

    # LEADER인 회원 삭제는 409
    r = client.delete(f"/api/admin/users/{S['leader_id']}", headers=_auth(S["admin_at"]))
    assert r.status_code == 409 and r.json()["code"] == "LEADER_PROJECT_EXISTS"


# ---------- 공지사항 ----------

def test_notices(client):
    # 관리자 CRUD — 일반 유저는 403
    assert client.post("/api/admin/notices", json={"title": "n", "body": "b"}, headers=_auth(S["member_at"])).status_code == 403
    assert client.post("/api/admin/notices", json={"title": "n", "body": "b", "category": "BAD"}, headers=_auth(S["admin_at"])).status_code == 400

    r = client.post("/api/admin/notices", json={"title": "정기 점검 안내", "body": "7/20 02시", "category": "SERVICE"}, headers=_auth(S["admin_at"]))
    assert r.status_code == 201, r.text
    normal_id = r.json()["id"]
    r = client.post("/api/admin/notices", json={"title": "v1.1 업데이트", "body": "버전관리 추가", "category": "UPDATE", "pinned": True}, headers=_auth(S["admin_at"]))
    assert r.status_code == 201
    pinned_id = r.json()["id"]

    # 사용자 목록 — pinned 우선 + 최신순, 미인증 401
    assert client.get("/api/notices").status_code == 401
    r = client.get("/api/notices", headers=_auth(S["member_at"]))
    assert r.status_code == 200 and r.json()["total_elements"] == 2
    assert [n["id"] for n in r.json()["items"]] == [pinned_id, normal_id]
    r = client.get("/api/notices", params={"category": "UPDATE"}, headers=_auth(S["member_at"]))
    assert r.json()["total_elements"] == 1

    # 상세 / 수정 / 삭제
    assert client.get(f"/api/notices/{normal_id}", headers=_auth(S["member_at"])).json()["title"] == "정기 점검 안내"
    r = client.patch(f"/api/admin/notices/{normal_id}", json={"pinned": True}, headers=_auth(S["admin_at"]))
    assert r.status_code == 200 and r.json()["pinned"] is True
    assert client.delete(f"/api/admin/notices/{pinned_id}", headers=_auth(S["admin_at"])).status_code == 204
    assert client.get(f"/api/notices/{pinned_id}", headers=_auth(S["member_at"])).status_code == 404
    assert client.get("/api/notices", headers=_auth(S["member_at"])).json()["total_elements"] == 1


def test_delegate_leave_and_withdraw(client):
    pid = S["pid"]
    # 팀장 위임 (멱등 PUT) → 기존 LEADER는 MEMBER로
    r = client.put(f"/api/projects/{pid}/leader", json={"user_id": S["member_id"]}, headers=_auth(S["leader_at"]))
    assert r.status_code == 200
    roles = {m["user_id"]: m["role"] for m in r.json()}
    assert roles[S["member_id"]] == "LEADER" and roles[S["leader_id"]] == "MEMBER"
    # 위임 후 기존 팀장은 탈퇴 가능
    assert client.delete(f"/api/projects/{pid}/members/me", headers=_auth(S["leader_at"])).status_code == 204
    assert client.get(f"/api/projects/{pid}", headers=_auth(S["leader_at"])).status_code == 403

    # 이제 LEADER가 아닌 leader1은 회원 탈퇴 가능
    assert client.delete("/api/users/me", headers=_auth(S["leader_at"])).status_code == 204
    assert _login(client, "leader1").status_code == 401  # Soft Delete → 로그인 불가
    # 3종 변형 저장으로 동일 값 재가입 가능
    assert _signup(client, "leader1", "리더킹", "leader@test.io").status_code == 201


def test_project_cascade_delete(client):
    pid = S["pid"]
    # 새 LEADER(member2)가 프로젝트 삭제 → 하위 Task cascade Soft Delete
    assert client.delete(f"/api/projects/{pid}", headers=_auth(S["member_at"])).status_code == 204
    assert client.get(f"/api/projects/{pid}", headers=_auth(S["member_at"])).status_code == 404
    assert client.get("/api/projects", headers=_auth(S["member_at"])).json()["total_elements"] == 0
    # Todo는 cascade 대상 아님 — member2의 Todo는 이미 비어 있으므로 생성해 확인 생략
