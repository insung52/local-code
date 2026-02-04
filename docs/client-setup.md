# 클라이언트 설치 가이드

> 새 컴퓨터에서 클라이언트 설정하기

---

## 요구사항

- Windows 10/11 (PowerShell)
- Python 3.10+
- Tailscale 설치 및 로그인

---

## 1. Tailscale 설치

1. https://tailscale.com/download/windows 다운로드
2. 설치 후 **서버와 같은 계정**으로 로그인

---

## 2. 코드 다운로드

```powershell
cd C:\graphics  # 또는 원하는 폴더
git clone https://github.com/YOUR_USERNAME/local-code.git
cd local-code
```

---

## 3. 설치 (자동)

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

이 스크립트가:
- PATH에 `llmcode` 명령어 등록
- Python 의존성 설치

---

## 4. 새 터미널 열고 실행

**중요: 설치 후 반드시 새 터미널 열기!**

```powershell
# 분석할 프로젝트 폴더로 이동
cd C:\your-project

# 실행
llmcode
```

**첫 실행 시 설정 입력:**
```
설정이 필요합니다.

서버 URL [http://100.104.99.20:8000]: (엔터)
API Key: your-api-key

설정 저장 완료!
```

---

## 5. 사용법

### 기본

```powershell
llmcode              # 대화형 모드
llmcode "질문"       # 바로 질문
llmcode -s           # 스캔 후 시작
llmcode -c           # 설정 변경
```

### 대화형 모드 명령어

| 명령어 | 설명 |
|--------|------|
| `/scan` | 현재 폴더 스캔 |
| `/clear` | 대화 초기화 |
| `/quit` | 종료 |

### 워크플로우 예시

```powershell
# 1. 프로젝트 폴더로 이동
cd C:\my-game-engine

# 2. llmcode 실행
llmcode

# 3. 첫 실행이면 스캔
> /scan

# 4. 질문하기
> 렌더링 파이프라인 구조 설명해줘
> 이 부분 최적화하려면?
```

---

## 설정 파일

| 위치 | 내용 |
|------|------|
| `~/.llmcode/config.json` | 서버 URL, API 키 |
| `프로젝트/.llmcode/` | 스캔 결과, 대화 기록 |

---

## 문제 해결

### "llmcode 명령을 찾을 수 없습니다"
- 새 터미널 열었는지 확인
- 안 되면 설치 다시: `powershell -ExecutionPolicy Bypass -File .\install.ps1`

### "서버 연결 실패"
- Tailscale 실행 중인지 확인
- 맥북 서버 켜져 있는지 확인
- `ping 100.104.99.20` 테스트

### 설정 변경하고 싶을 때
```powershell
llmcode -c
```

---

## 빠른 시작

```powershell
# 1. Tailscale 설치 + 로그인
# 2. 코드 받기
git clone https://github.com/YOUR_USERNAME/local-code.git
cd local-code

# 3. 설치
powershell -ExecutionPolicy Bypass -File .\install.ps1

# 4. 새 터미널 열고, 프로젝트 폴더에서
cd C:\my-project
llmcode
```
