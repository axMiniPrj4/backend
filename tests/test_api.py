"""전체 도메인 통합 스모크 테스트 — 정의 순서대로 실행되며 상태를 공유한다."""
import io

S = {}  # 테스트 간 공유 상태 (토큰, id 등)

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100  # 더미 파일 내용


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _signup(client, login_id, nickname, email):
    return client.post("/api/auth/signup", json={
        "login_id": login_id, "password": "password1!", "name": "홍길동",
        "nickname": nickname, "email": email,
    })


def _login(client, login_id, password="password1!"):
    return client.post("/api/auth/login", json={"login_id": login_id, "password": password})


# ---------- Health / Auth ----------

def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_signup_and_duplicates(client):
    r = _signup(client, "leader1", "리더", "leader@test.io")
    assert r.status_code == 201, r.text
    assert r.json()["plan"] == "FREE"
    assert _signup(client, "member2", "멤버", "member@test.io").status_code == 201
    assert _signup(client, "other3", "아웃사이더", "other@test.io").status_code == 201

    assert _signup(client, "leader1", "다른닉", "x@test.io").json()["code"] == "DUPLICATE_LOGIN_ID"
    assert _signup(client, "newid99", "리더", "x@test.io").json()["code"] == "DUPLICATE_NICKNAME"
    assert _signup(client, "newid99", "다른닉", "leader@test.io").json()["code"] == "DUPLICATE_EMAIL"

    # 비밀번호 정책: 8~16자, 영문+숫자+특수문자
    for bad in ("short1!", "password12", "verylongpassword1!"):  # 길이 미달 / 특수문자 없음 / 길이 초과
        r = client.post("/api/auth/signup", json={
            "login_id": "badpw123", "password": bad, "name": "n", "nickname": "badpw", "email": "badpw@test.io",
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

    # 수정: 작성자/LEADER만 (member2는 둘 다 아님 → 403). 담당자 교체는 전체 교체
    assert client.patch(f"{url}/{S['task_member']}", json={"title": "변경"}, headers=_auth(S["member_at"])).status_code == 403
    r = client.patch(f"{url}/{S['task_member']}", json={"title": "변경됨", "assignee_ids": [S["member_id"]]}, headers=_auth(S["leader_at"]))
    assert r.status_code == 200 and [a["id"] for a in r.json()["assignees"]] == [S["member_id"]]
    # 담당자 비우기는 불가 (최소 1명)
    assert client.patch(f"{url}/{S['task_member']}", json={"assignee_ids": []}, headers=_auth(S["leader_at"])).status_code == 400

    # 상태 변경: 담당자 중 한 명/LEADER — member2는 자기 담당 업무만 가능
    assert client.patch(f"{url}/{S['task_leader']}/status", json={"status": "DONE"}, headers=_auth(S["member_at"])).status_code == 403
    assert client.patch(f"{url}/{S['task_member']}/status", json={"status": "DONE"}, headers=_auth(S["member_at"])).status_code == 200
    assert client.patch(f"{url}/{S['task_member']}/status", json={"status": "BAD"}, headers=_auth(S["member_at"])).status_code == 400

    r = client.get(url, params={"status": "DONE"}, headers=_auth(S["member_at"]))
    assert r.status_code == 200 and r.json()["total_elements"] == 1
    # 담당자 필터: member2가 담당인 업무만
    r = client.get(url, params={"assignee_id": S["member_id"]}, headers=_auth(S["member_at"]))
    assert r.status_code == 200 and r.json()["total_elements"] == 1


def test_gantt(client):
    r = client.get(f"/api/projects/{S['pid']}/gantt", headers=_auth(S["member_at"]))
    assert r.status_code == 200
    body = r.json()
    assert body["total_tasks"] == 2 and body["done_tasks"] == 1 and body["progress"] == 50.0
    assert body["tasks"][0]["assignees"][0]["nickname"]


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

    # 게시글 삭제(작성자) → 조회 404
    assert client.delete(f"{url}/{S['doc_id']}", headers=_auth(S["leader_at"])).status_code == 204
    assert client.get(f"{url}/{S['doc_id']}", headers=_auth(S["member_at"])).status_code == 404


# ---------- 전역 자료실 (공통 자료 + 내 프로젝트 자료) ----------

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
