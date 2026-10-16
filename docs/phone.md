# 폰에서 쓰기 (Tailscale)

서버는 집 Mac에서 돌리고, 폰은 Tailscale로 접속한다(결정 D1). Tailscale Serve는 내 tailnet 기기에만 HTTPS 주소를 연다. 인터넷에 공개하지 않는다(Funnel을 쓰지 않는다). 서버 API에는 로그인이 없으므로 공개 주소로 열면 안 된다.

## 처음 한 번

1. Tailscale 관리 콘솔에서 Serve를 허용한다.
   - DNS 페이지(https://login.tailscale.com/admin/dns)에서 MagicDNS와 HTTPS Certificates를 켠다.
   - `./run.sh --phone`이 허용 링크를 보여 주면 그 링크를 열어 허용한다.
2. 폰에 Tailscale 앱을 설치하고 Mac과 같은 계정으로 로그인한다.

## 실행

```bash
./run.sh --phone          # 실제 Claude CLI(구독 사용량)
./run.sh --phone --fake   # 가짜 CLI·가짜 음성(화면 확인용, 사용량 없음)
```

- 웹을 빌드해 서버(8000)가 함께 서빙하고, `https://<Mac 이름>.<tailnet>.ts.net/` 주소를 출력한다. 이 주소는 실행할 때마다 바뀌지 않는다(Mac의 Tailscale 기기 이름). 바꾸려면 관리 콘솔 Machines에서 기기 이름을 바꾼다(예: `trailtalk` → `https://trailtalk.<tailnet>.ts.net/`).
- 포트 8000을 쓰는 다른 서버(`./run.sh` 등)가 떠 있으면 먼저 끈다(`./stop.sh`).
- 실행 중에는 Mac이 잠들지 않게 한다(`caffeinate`). 덮개를 닫고 배터리로 쓰면 그래도 잠들 수 있으니 전원을 연결해 둔다.
- Ctrl+C로 끝내면 HTTPS 주소도 닫힌다(`tailscale serve --https=443 off`). 이 Mac의 443에 다른 Serve 설정이 있으면 덮어쓰고 지운다.
- 다른 터미널에서 끄거나, 스크립트가 강제로 죽어 서버·Serve 설정이 남았으면(502) `./stop.sh`를 실행한다. 이 저장소의 프로세스만 끄고, 443의 `/`가 이 서버를 가리킬 때만 Serve를 닫는다(닫을 때는 443 설정 전체).

## 폰에서

1. 폰의 Tailscale을 켠다.
2. Chrome에서 출력된 주소를 연다.
3. "음성으로 대화"를 누르고 마이크를 허용한다.
4. 메뉴의 "홈 화면에 추가"(앱 설치)를 누르면 앱처럼 열 수 있다.

- 앱 화면은 저장돼 있어서, 연결이 끊긴 채 다시 열어도 화면이 뜬다.
- 음성 감지 자산(약 14MB)은 앱을 두 번째로 연 뒤(첫 방문 때는 서비스 워커가 아직 페이지를 맡지 않는다) 음성 대화를 할 때 저장된다. 산에 가기 전에 집에서 한 번 다시 열어 음성 대화를 해 두면, 그 뒤에는 연결이 끊겨도 말이 기기에 보관됐다가 연결되면 보내진다.
- Mac에서 새 버전으로 실행하면 폰 화면 위에 "새 버전 적용" 버튼이 나온다. 대화를 마친 뒤 누른다(대화 중에는 자동으로 새로 고치지 않는다).

## 보안

- 앱 도구 경로 `/internal/*`은 프록시를 거친 요청을 서버가 403으로 막는다. Tailscale Serve는 `X-Forwarded-Host`를 늘 붙이고 `X-Forwarded-For`도 더한다(`Tailscale-User-Login`은 사람 계정 기기일 때만 붙어 보조 수단이다). 각 요청에는 대화 세션 토큰도 필요하다.
- tailnet에 다른 사람을 초대하면 그 사람도 이 앱에 접속할 수 있다. 공유하기 전에 Tailscale ACL로 이 Mac에 대한 접근을 제한한다.
