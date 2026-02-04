# 맥북 서버 배포 가이드

> MacBook Air M3 16GB 기준

---

## 1. Ollama 설치

```bash
# Homebrew로 설치
brew install ollama

# 또는 공식 사이트에서 다운로드
# https://ollama.ai/download/mac
```

**Ollama 실행:**
```bash
# 백그라운드 서비스로 실행 (권장)
brew services start ollama

# 또는 직접 실행
ollama serve
```

---

## 2. 모델 다운로드

```bash
# 메인 모델 (코드 분석용) - 약 9GB
ollama pull qwen2.5-coder:14b

# 임베딩 모델 - 약 300MB
ollama pull nomic-embed-text

# (선택) 빠른 요약용 경량 모델
ollama pull llama3.2:3b
```

**다운로드 확인:**
```bash
ollama list
```

---

## 3. 코드 가져오기

```bash
cd ~
mkdir -p projects
cd projects

# GitHub에서 clone
git clone https://github.com/YOUR_USERNAME/local-code.git
cd local-code
```

**디렉토리 구조:**
```
~/projects/local-code/
├── server/          # 서버 (맥북에서 실행)
├── client/          # 클라이언트 (다른 PC에서 실행)
├── docs/
├── api-spec.md
└── plan.md
```

---

## 4. Python 환경 설정

```bash
# Python 3.10+ 확인
python3 --version

# 가상환경 생성
cd ~/projects/local-code/server
python3 -m venv venv
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt
```

---

## 5. 환경 설정

```bash
# .env 파일 생성
cp .env.example .env

# .env 편집
nano .env
```

**.env 내용:**
```bash
HOST=0.0.0.0
PORT=8000

# 강력한 API 키 생성 (필수!)
API_KEYS=your-secure-api-key-here

OLLAMA_BASE_URL=http://localhost:11434
RATE_LIMIT=60/minute

DEFAULT_CHAT_MODEL=qwen2.5-coder:14b
DEFAULT_EMBED_MODEL=nomic-embed-text
```

**API 키 생성 (터미널에서):**
```bash
# 랜덤 키 생성
openssl rand -hex 32
```

---

## 6. 서버 실행

```bash
cd ~/projects/local-code/server
source venv/bin/activate
python main.py
```

**출력 예시:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

---

## 7. 로컬 테스트

**새 터미널에서:**
```bash
# 헬스체크
curl http://localhost:8000/api/v1/health \
  -H "X-API-Key: your-secure-api-key-here"

# 모델 목록
curl http://localhost:8000/api/v1/models \
  -H "X-API-Key: your-secure-api-key-here"
```

---

## 8. 공유기 포트포워딩

### 8-1. 맥북 내부 IP 확인

```bash
# WiFi IP 확인
ipconfig getifaddr en0
# 예: 192.168.0.10
```

### 8-2. 공유기 설정

1. 공유기 관리 페이지 접속 (보통 `192.168.0.1` 또는 `192.168.1.1`)
2. 포트포워딩 / 가상서버 메뉴 찾기
3. 규칙 추가:
   - 외부 포트: `8000` (또는 원하는 포트)
   - 내부 IP: `192.168.0.10` (맥북 IP)
   - 내부 포트: `8000`
   - 프로토콜: TCP

### 8-3. 외부 IP 확인

```bash
curl ifconfig.me
# 예: 123.456.789.10
```

### 8-4. DDNS 설정 (선택, 권장)

IP가 변경될 수 있으므로 DDNS 사용 권장:
- [No-IP](https://www.noip.com/) (무료)
- [DuckDNS](https://www.duckdns.org/) (무료)

예: `your-server.duckdns.org`

---

## 9. 클라이언트 설정

**클라이언트 PC에서:**

```bash
cd client

# 서버 주소로 초기화
python cli.py init \
  --server http://your-external-ip:8000 \
  --api-key your-secure-api-key-here

# 또는 DDNS 사용 시
python cli.py init \
  --server http://your-server.duckdns.org:8000 \
  --api-key your-secure-api-key-here
```

**연결 테스트:**
```bash
python cli.py status
```

---

## 10. 백그라운드 실행 (선택)

### 방법 1: tmux 사용

```bash
# tmux 설치
brew install tmux

# 새 세션 시작
tmux new -s llmcode

# 서버 실행
cd ~/projects/local-code/server
source venv/bin/activate
python main.py

# 세션 분리: Ctrl+B, D

# 나중에 세션 복귀
tmux attach -t llmcode
```

### 방법 2: launchd 서비스 등록

**~/Library/LaunchAgents/com.llmcode.server.plist:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.llmcode.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USERNAME/projects/local-code-server/venv/bin/python</string>
        <string>/Users/YOUR_USERNAME/projects/local-code-server/main.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/YOUR_USERNAME/projects/local-code-server</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/llmcode-server.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/llmcode-server.err</string>
</dict>
</plist>
```

**서비스 등록:**
```bash
launchctl load ~/Library/LaunchAgents/com.llmcode.server.plist

# 서비스 확인
launchctl list | grep llmcode

# 서비스 중지
launchctl unload ~/Library/LaunchAgents/com.llmcode.server.plist
```

---

## 11. HTTPS 설정 (선택, 보안 강화)

외부 노출 시 HTTPS 권장.

### 방법 1: Cloudflare Tunnel (무료, 권장)

```bash
# cloudflared 설치
brew install cloudflared

# 로그인
cloudflared tunnel login

# 터널 생성
cloudflared tunnel create llmcode

# 설정 파일 생성
# ~/.cloudflared/config.yml
```

**~/.cloudflared/config.yml:**
```yaml
tunnel: YOUR_TUNNEL_ID
credentials-file: /Users/YOUR_USERNAME/.cloudflared/YOUR_TUNNEL_ID.json

ingress:
  - hostname: llmcode.your-domain.com
    service: http://localhost:8000
  - service: http_status:404
```

```bash
# 터널 실행
cloudflared tunnel run llmcode
```

### 방법 2: Self-signed 인증서

```bash
# 인증서 생성
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes

# main.py 수정하여 SSL 적용 (uvicorn 옵션)
```

---

## 문제 해결

### Ollama 연결 안 됨
```bash
# Ollama 상태 확인
curl http://localhost:11434/api/version

# Ollama 재시작
brew services restart ollama
```

### 모델 로딩 느림
- 첫 요청 시 모델 로딩에 시간 소요 (정상)
- M3 16GB에서 qwen2.5-coder:14b는 약 30초~1분 로딩

### 메모리 부족
```bash
# 메모리 확인
vm_stat

# 가벼운 모델로 교체
# .env에서 DEFAULT_CHAT_MODEL=llama3.2:3b
```

### 포트포워딩 안 됨
- 공유기 방화벽 확인
- ISP에서 포트 차단 여부 확인
- 다른 포트 시도 (8080, 8443 등)

---

## 체크리스트

- [ ] Ollama 설치 및 실행
- [ ] 모델 다운로드 (qwen2.5-coder:14b, nomic-embed-text)
- [ ] 서버 코드 복사
- [ ] Python 가상환경 설정
- [ ] .env 파일 설정 (API 키!)
- [ ] 서버 실행 및 로컬 테스트
- [ ] 포트포워딩 설정
- [ ] 클라이언트에서 연결 테스트
- [ ] (선택) DDNS 설정
- [ ] (선택) 백그라운드 실행 설정
- [ ] (선택) HTTPS 설정
