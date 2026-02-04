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

## 8. Tailscale 설정 (보안 네트워크)

Tailscale은 WireGuard 기반 VPN으로, 포트포워딩 없이 안전하게 연결 가능.

### 8-1. 맥북에 Tailscale 설치

```bash
# Homebrew로 설치
brew install tailscale

# Tailscale 시작
sudo tailscaled &

# 로그인 (브라우저 열림)
tailscale up
```

또는 [Tailscale 공식 사이트](https://tailscale.com/download/mac)에서 앱 다운로드.

### 8-2. 클라이언트 PC에 Tailscale 설치

**Windows:**
1. https://tailscale.com/download/windows 에서 다운로드
2. 설치 후 같은 계정으로 로그인

**Linux:**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

### 8-3. 맥북 Tailscale IP 확인

```bash
tailscale ip -4
# 예: 100.64.0.1
```

또는 Tailscale 앱/웹 대시보드에서 확인.

### 8-4. 연결 테스트

클라이언트 PC에서:
```bash
# 맥북 Tailscale IP로 ping
ping 100.64.0.1

# 서버 접속 테스트
curl http://100.64.0.1:8000/api/v1/health -H "X-API-Key: your-key"
```

### 장점
- 포트포워딩 필요 없음
- 자동 암호화 (WireGuard)
- IP 고정 (재부팅해도 동일)
- 무료 (개인 사용)

---

## 9. 클라이언트 설정

**클라이언트 PC에서:**

```bash
cd client

# Tailscale IP로 초기화 (맥북의 Tailscale IP 사용)
python cli.py init \
  --server http://100.64.0.1:8000 \
  --api-key your-secure-api-key-here
```

**연결 테스트:**
```bash
python cli.py status
```

**참고:** `100.64.0.1`은 예시. 실제 맥북의 Tailscale IP로 교체.

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

## 11. 보안 참고사항

### Tailscale 사용 시
- Tailscale은 WireGuard로 **자동 암호화**됨
- 추가 HTTPS 설정 불필요
- Tailscale 네트워크 외부에서는 접근 불가 (안전)

### 추가 보안 (선택)
- API 키를 강력하게 설정 (`openssl rand -hex 32`)
- Rate limiting 활성화됨 (기본 60회/분)
- 필요시 `.env`에서 `RATE_LIMIT` 조정

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

### Tailscale 연결 안 됨
```bash
# Tailscale 상태 확인
tailscale status

# 재연결
tailscale down && tailscale up
```
- 양쪽 기기가 같은 Tailscale 계정인지 확인
- 방화벽에서 Tailscale 허용 확인

---

## 체크리스트

- [ ] Ollama 설치 및 실행
- [ ] 모델 다운로드 (`qwen2.5-coder:14b`, `nomic-embed-text`)
- [ ] GitHub에서 코드 clone
- [ ] Python 가상환경 설정 + 의존성 설치
- [ ] .env 파일 설정 (API 키!)
- [ ] 서버 실행 및 로컬 테스트
- [ ] Tailscale 설치 (맥북 + 클라이언트 PC)
- [ ] 클라이언트에서 Tailscale IP로 연결 테스트
- [ ] (선택) 백그라운드 실행 설정 (tmux/launchd)
