# DevHire Insight — 배포 가이드

운영 배포 구조와 재배포 방법. (개발/로컬 실행은 `RUN.md` 참고)

`<...>` 는 각자 값으로 치환한다. (예: `<도메인>` = 발급받은 DuckDNS 서브도메인)

## 구조 한눈에

```
[GitHub repo] --push--> Vercel (frontend 자동 빌드·배포)

브라우저 --HTTPS--> Vercel(정적 파일)
   └── 브라우저 JS --HTTPS--> <도메인>  (Lightsail: nginx → uvicorn)
                                   └── 127.0.0.1:3306 MariaDB (같은 인스턴스)
```

| 조각 | 위치 | 주소 |
|---|---|---|
| 프론트 | Vercel | `https://<프론트>.vercel.app` |
| 백엔드 | Lightsail (Ubuntu 22.04) | `https://<도메인>` |
| DB | 인스턴스 내부 MariaDB | 외부 비공개, 백엔드는 localhost |

- 백엔드 서비스명: `devhire-api` (systemd)
- 도메인: 무료 DDNS(DuckDNS 등) 서브도메인 → 인스턴스 고정 IP 연결

---

## 재배포 (일상)

| 무엇을 바꿨나 | 할 일 |
|---|---|
| **프론트** (`frontend/`) | **아무것도 안 함** — master push하면 Vercel 자동 배포 |
| **백엔드** (`fastapi_app/`) | 인스턴스에서 `cd ~/DevHire_Insight && git pull && sudo systemctl restart devhire-api` |
| **데이터** (크롤/마트) | 로컬에서 `run_crawler.py` → `build_mart.py` (서버 재시작 불필요, 새로고침하면 반영) |

백엔드 상태/로그:
```bash
sudo systemctl status devhire-api --no-pager
sudo journalctl -u devhire-api -n 50 --no-pager
```

---

## 백엔드 초기 배포 (Lightsail, 재구축 시)

### 0. 사전
- 인스턴스에 **고정 IP** attach, 방화벽 **80·443** 오픈(소스 Any)
- DDNS 서브도메인 → 고정 IP 연결 (`nslookup <도메인>` 으로 확인)

### 1. 코드 받기 (private repo → deploy key)
```bash
ssh-keygen -t ed25519 -C "lightsail-deploy" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub    # GitHub 저장소 Settings → Deploy keys 에 등록(읽기전용)
ssh -T git@github.com        # 인증 확인
git clone git@github.com:<계정>/DevHire_Insight.git ~/DevHire_Insight
```

### 2. 파이썬 환경
```bash
cd ~/DevHire_Insight
sudo apt install -y python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r fastapi_app/requirements.txt
```

### 3. `.env` (프로젝트 루트)
```
DB_HOST=127.0.0.1          # ⚠️ 반드시 localhost. 공인 IP 쓰면 방화벽 제한 시 끊김
DB_PORT=3306
DB_NAME=<db 이름>
DB_USER=<db 유저>
DB_PASSWORD=<비밀번호>
CORS_ORIGINS=https://<프론트>.vercel.app,http://localhost:5173
```

### 4. systemd 서비스 (`/etc/systemd/system/devhire-api.service`)
```ini
[Unit]
Description=DevHire FastAPI
After=network.target mariadb.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/DevHire_Insight/fastapi_app
ExecStart=/home/ubuntu/DevHire_Insight/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now devhire-api
curl -s localhost:8000/health        # {"status":"ok"}
```

### 5. nginx 리버스 프록시 (`/etc/nginx/sites-available/devhire`)
```nginx
server {
    listen 80;
    server_name <도메인>;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
```bash
sudo ln -sf /etc/nginx/sites-available/devhire /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### 6. HTTPS (Let's Encrypt)
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d <도메인>     # 리다이렉트 Yes
curl -s https://<도메인>/health
```

---

## 프론트 배포 (Vercel)

GitHub 연동 → master push 시 **자동 배포**. 초기 설정:
- **Root Directory**: `frontend` (모노레포라 필수)
- **Framework Preset**: Vite (자동)
- **환경변수**: `VITE_API_BASE = https://<도메인>`

백엔드 CORS 는 `.env` 의 `CORS_ORIGINS` 에 프론트 도메인만 넣는다.
프론트 도메인이 바뀌면 그 값을 갱신한 뒤 백엔드를 재시작한다.

---

## DB 보안

- MariaDB `bind-address=0.0.0.0`, 유저 `<db유저>@%` 존재 → 방화벽으로 노출을 통제한다.
- **방화벽 3306**: 소스를 **로컬 작업 PC의 고정 IP만** 허용. 백엔드는 `127.0.0.1` 이라 이 제한과 무관.
- IP가 바뀌는 환경에서 로컬 크롤/마트가 필요하면 3306을 열지 말고 **SSH 터널** 사용:
  ```bash
  ssh -i <pem키> -L 3306:127.0.0.1:3306 ubuntu@<고정IP>
  # 로컬 .env 의 DB_HOST=127.0.0.1 로 두고 스크립트 실행
  ```
- (선택) 추가 강화: `<db유저>@%` 삭제 + `<db유저>@'127.0.0.1'` 생성.

---

## 함정 메모 (겪은 것들)

- **백엔드 `.env` 의 `DB_HOST` 는 반드시 `127.0.0.1`.** 공인 IP로 두면 3306 방화벽을 특정 IP로 제한하는 순간 백엔드가 자기 자신에 못 붙어 500 에러.
- systemd/nginx 설정을 heredoc(`<<'EOF'`)으로 만들 때 **닫는 `EOF` 앞에 공백이 있으면** 안 닫힘 → `nano` 로 만드는 게 안전.
- certbot 전에 **방화벽 443** 열려 있어야 함.
- CORS 는 Vercel **production 도메인**(Domains 탭)만 넣기. deployment(해시) 주소는 배포마다 바뀜.
