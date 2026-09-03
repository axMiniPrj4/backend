# 리버스 프록시 설정 (work.yangju.kr)

Nginx Proxy Manager(NPM) 컨테이너가 도메인 5개를 함께 받고 있고, 그중
`work.yangju.kr` 이 이 서비스다. NPM 설정은 컨테이너 안 `/data/database.sqlite`
에만 남고 저장소에는 없어서, 서버를 옮기면 다시 넣어야 한다. **여기 적힌 내용이
그 복원 기준이다.**

NPM 관리 화면 → Proxy Hosts → `work.yangju.kr` (id 5) 에서 아래대로 맞춘다.

## Details

| 항목 | 값 |
|---|---|
| Domain Names | `work.yangju.kr` |
| Scheme / Forward Host / Port | `http` / `ohapjijol-backend` / `8000` |
| **Websockets Support** | **켬** |

기본 Forward 대상이 백엔드지만, 아래 Custom locations 와 Advanced 설정 때문에
실제로 여기로 오는 요청은 없다. NPM 이 값을 요구해서 남겨 둔 것이다.

## Custom locations

| Location | Scheme | Forward Host | Port |
|---|---|---|---|
| `/api/` | http | `ohapjijol-backend` | 8000 |
| `/health` | http | `ohapjijol-backend` | 8000 |
| `/user/` | http | `ohapjijol-frontend-user` | 80 |
| `/admin/` | http | `ohapjijol-frontend-admin` | 80 |

- 백엔드 라우터는 전부 `/api` 로 시작한다. 예외는 `GET /health` 하나뿐인데,
  사용자 프론트가 연동 확인용으로 직접 부르기 때문에(`services/apiClient.js`)
  따로 열어 둬야 한다.
- 웹소켓은 `/api/projects/{id}/{chat|erd|whiteboard|workspace|video}/ws` 로 붙는다.
  Websockets Support 를 켜야 `Upgrade` 헤더가 전달된다.

## Advanced

```nginx
location / {
  return 302 /user/;
}
```

- 루트로 들어오면 사용자 화면으로 보낸다. 예전에는 `/` 가 백엔드로 흘러가
  `{"code":"NOT_FOUND"}` JSON 이 그대로 보였다.
- NPM 은 Advanced 설정에 `location /` 가 있으면 자기 기본 블록을 만들지 않는다
  (`/app/internal/nginx.js` 의 `advancedConfigHasDefaultLocation`). 그래서
  중복 없이 이 블록이 catch-all 이 된다.
- 부수 효과로 `/docs`, `/redoc`, `/openapi.json` 도 `/user/` 로 넘어가
  외부에서 API 스펙을 열 수 없다. 개발 중에 문서가 필요하면 컨테이너로 직접
  붙거나(`docker exec ... curl localhost:8000/docs`) 이 블록을 잠시 비운다.

## 확인 방법

```sh
docker exec nginx-proxy-manager sh -c '
for p in / /user/ /admin/ /health /docs /nope; do
  printf "%-10s -> " $p
  curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" -H "Host: work.yangju.kr" http://127.0.0.1$p
done'
```

기대값

```
/          -> 302 http://work.yangju.kr/user/
/user/     -> 200
/admin/    -> 200
/health    -> 200
/docs      -> 302 http://work.yangju.kr/user/
/nope      -> 302 http://work.yangju.kr/user/
```

## 주의

- NPM 컨테이너를 재시작하면 DB 기준으로 conf 가 다시 만들어진다. 설정을 손으로
  고칠 때는 `/data/nginx/proxy_host/5.conf` 만 고치지 말고 DB(=관리 화면)도 함께
  맞춰야 한다. 그렇지 않으면 재시작 때 되돌아간다.
- 같은 NPM 이 `dns.yangju.kr`, `info.yangju.kr`, `s.kr`, `work.net` 도 받는다.
  설정을 바꾼 뒤에는 `nginx -t` 로 검증하고 `nginx -s reload` 만 한다.
  컨테이너를 재시작하면 다른 도메인까지 잠시 끊긴다.

## 아직 남은 것

웹소켓은 프록시 쪽 준비만 끝났다. 백엔드 이미지에 `websockets` 패키지가 없어
uvicorn 이 업그레이드 요청을 처리하지 못하고 404 를 돌려준다. 실시간 협업
(채팅·화이트보드·ERD·워크스페이스·화상)을 살리려면 `requirements.txt` 에
`websockets` 를 추가하고 백엔드를 다시 빌드해야 한다.
