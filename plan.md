# Local Code Assistant - 구현 계획 (v4)

> 로컬 LLM 기반 대화형 코드 에이전트

---

## 현재 상태

| Phase | 상태 | 내용 |
|-------|------|------|
| Phase 1 | ✅ 완료 | 서버 MVP, API, 인증 |
| Phase 2 | ✅ 완료 | RAG, 임베딩, 요약 |
| Phase 3 | ✅ 완료 | 에이전트 루프, ESC 중지, 파일 수정 확인 |
| Phase 4 | ✅ 완료 | Git 연동, 명령 실행 |

---

## 아키텍처

```
[ Client PC ]                              [ MacBook M3 ]
┌─────────────────────┐                   ┌─────────────────────┐
│  CLI (Python)       │                   │  FastAPI Server     │
│  ├─ Agent Loop      │   Tailscale       │  ├─ Auth Middleware │
│  ├─ Tool Executor   │ ───────────────►  │  ├─ Ollama Client   │
│  │   ├─ list_files  │ ◄─────────────────│  └─ SSE Streaming   │
│  │   ├─ read_file   │      (SSE)        │                     │
│  │   ├─ search_code │                   └─────────────────────┘
│  │   ├─ write_file  │                            │
│  │   ├─ git_status  │                            │
│  │   ├─ git_diff    │                            │
│  │   └─ run_command │                            │
│  └─ Context Manager │                            ▼
└─────────────────────┘                        Ollama
                                           qwen2.5-coder:14b
```

---

## 완료된 기능

### Phase 1 - MVP
- [x] FastAPI 서버 + Ollama 연동
- [x] SSE 스트리밍
- [x] API Key 인증
- [x] Rate limiting

### Phase 2 - 컨텍스트 관리
- [x] 파일 요약 + SQLite 저장
- [x] 임베딩 + ChromaDB
- [x] RAG 검색

### Phase 3 - Claude Code 스타일
- [x] 에이전트 루프 (도구 호출 → 실행 → 반복)
- [x] 기본 도구: list_files, read_file, search_code, write_file
- [x] ESC로 응답 중지
- [x] 파일 수정 시 diff + y/n 확인
- [x] /include, /scan, /clear 명령어
- [x] 간편 설치 (install.ps1)
- [x] 간결한 응답 스타일

### Phase 4 - 고급 도구
- [x] git_status, git_diff 도구
- [x] run_command 도구 (y/n 확인)

---

## Phase 4 - 고급 기능

### 4-1. Git 연동
- [x] `git_status` 도구 - 변경된 파일 목록
- [x] `git_diff` 도구 - 변경 내용 확인
- [ ] 증분 스캔 (변경된 파일만 재인덱싱)

### 4-2. 코드 실행
- [x] `run_command` 도구 - 터미널 명령 실행 (y/n 확인)
- [x] 테스트 실행 지원
- [x] 빌드 명령 실행

### 4-3. 개선사항 (선택)
- [ ] 대화 히스토리 압축 (토큰 절약)
- [ ] 응답 캐싱
- [ ] 에러 재시도 로직

---

## Phase 5 - 나중에 (선택)

-git clone 안하고도 간단하게 클라이언트 사용할 수 있는 방법 만들기 (.exe 설치 파일 느낌)

### 5-1. 멀티 모델
- [ ] 요약용 경량 모델 (llama3.2:3b)
- [ ] 분석용 메인 모델 (qwen2.5-coder:14b)
- [ ] 모델 자동 선택

### 5-2. Claude API Fallback
- [ ] 복잡한 질문은 Claude API로
- [ ] 비용 제한 설정

---

## 사용법

```bash
# 설치
git clone https://github.com/YOUR_USERNAME/local-code.git
cd local-code
powershell -ExecutionPolicy Bypass -File .\install.ps1

# 새 터미널에서
cd your-project
llmcode

# 명령어
/scan    - 프로젝트 스캔
/include - 파일 추가
/clear   - 대화 초기화
/quit    - 종료
ESC      - 응답 중지
```

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| 서버 | FastAPI, Uvicorn, SSE |
| 클라이언트 | Click, httpx, Rich, ChromaDB |
| 네트워크 | Tailscale VPN |
| LLM | Ollama (qwen2.5-coder:14b) |

---

## 다음 작업

선택적 개선사항:
1. **증분 스캔** - git status로 변경된 파일만 재인덱싱
2. **대화 압축** - 긴 대화 요약해서 토큰 절약
3. **간편 설치** - git clone 없이 .exe 설치파일 배포
4. **멀티 모델** - Phase 5

