# Local Code Assistant - 구현 계획 (v2)

> 로컬 LLM 기반 원격 코드 분석 도구

---

## 요구사항 정의

| 구분 | 내용 |
|------|------|
| **서버 (맥북에어 M3 16GB)** | Ollama + FastAPI, LLM 추론 담당 |
| **클라이언트 (다른 PC)** | Python CLI, 파일 시스템 접근 + 컨텍스트 관리 |
| **네트워크** | 포트포워딩으로 외부 노출 → 인증 필수 |
| **언어** | Python (서버/클라이언트 통일) |
| **우선순위** | 정확도 > 속도 |

---

## 하드웨어 제약 및 모델 선택

### M3 16GB 환경 추천 모델

| 용도 | 모델 | 크기 | 컨텍스트 | 비고 |
|------|------|------|----------|------|
| **코드 분석 (메인)** | `deepseek-coder-v2:16b` | ~9GB | 128K | 코드 특화, 긴 컨텍스트 |
| **코드 분석 (대안)** | `codellama:13b` | ~7GB | 16K | 안정적 |
| **가벼운 요약** | `llama3.2:3b` | ~2GB | 128K | 빠른 응답 |
| **임베딩** | `nomic-embed-text` | ~300MB | 8K | 벡터 검색용 |

> 16GB에서 메인 모델 + 임베딩 모델 동시 로드 가능

---

## 아키텍처

```
[ Client PC ]                              [ MacBook M3 ]
┌─────────────────────┐                   ┌─────────────────────┐
│  CLI (Python)       │                   │  FastAPI Server     │
│  ├─ File Scanner    │   HTTPS + Auth    │  ├─ Auth Middleware │
│  ├─ Code Chunker    │ ───────────────►  │  ├─ Ollama Client   │
│  ├─ Embeddings DB   │ ◄─────────────────│  ├─ SSE Streaming   │
│  └─ Context Manager │      (SSE)        │  └─ Embedding API   │
└─────────────────────┘                   └─────────────────────┘
        │                                          │
        ▼                                          ▼
   .llmcode/                                   Ollama
   ├─ config.json                             ├─ deepseek-coder
   ├─ summaries.db (SQLite)                   └─ nomic-embed-text
   ├─ vectors.db (ChromaDB)
   └─ history.json
```

**핵심 원칙:**
1. 서버는 파일 시스템을 모른다
2. CLI가 컨텍스트의 주인
3. 모든 응답은 스트리밍

---

## 보안 설계

### 인증 방식: API Key + Rate Limiting

```python
# 서버 설정 예시
AUTH_CONFIG = {
    "api_keys": ["your-secret-key-here"],  # 환경변수로 관리
    "rate_limit": "60/minute",
    "allowed_ips": ["*"],  # 또는 특정 IP만
}
```

### 보안 체크리스트
- [ ] HTTPS (Let's Encrypt 또는 self-signed)
- [ ] API Key 헤더 검증 (`X-API-Key`)
- [ ] Rate limiting (slowapi)
- [ ] 요청 크기 제한 (10MB)
- [ ] 로깅 (접근 기록)

---

## Phase 1 - MVP (기반 구축)

### 목표
> CLI에서 파일 전송 → 서버가 스트리밍 응답 반환

### 서버 구현

```
server/
├── main.py              # FastAPI 앱
├── auth.py              # API Key 미들웨어
├── ollama_client.py     # Ollama 연동 (스트리밍)
├── routes/
│   ├── analyze.py       # POST /analyze (SSE)
│   └── health.py        # GET /health
└── requirements.txt
```

**API 스펙:**

```http
POST /api/v1/analyze
Content-Type: application/json
X-API-Key: your-secret-key

{
  "files": [
    {"path": "src/renderer.cpp", "content": "..."}
  ],
  "prompt": "이 코드의 병목 지점을 찾아줘",
  "model": "deepseek-coder-v2:16b",
  "stream": true
}

Response: text/event-stream
data: {"token": "이", "done": false}
data: {"token": " 코드는", "done": false}
...
data: {"token": "", "done": true, "total_tokens": 1234}
```

### 클라이언트 구현

```
client/
├── cli.py               # Click 기반 CLI
├── scanner.py           # 파일 스캔 + 필터링
├── chunker.py           # 토큰 기반 청킹
├── api_client.py        # 서버 통신 (httpx + SSE)
├── config.py            # 설정 관리
└── requirements.txt
```

**CLI 명령어:**

```bash
# 초기 설정
llmcode init --server https://your-macbook.ddns.net:8000 --api-key xxx

# 단일 파일 분석
llmcode ask "이 함수 설명해줘" src/main.cpp

# 디렉토리 분석
llmcode ask "렌더링 구조 설명해줘" ./src --ext .cpp,.h
```

---

## Phase 2 - 컨텍스트 관리 (핵심)

### 목표
> 대규모 코드베이스를 효율적으로 분석

### 2-1. 계층적 요약

```
파일 → 파일 요약 → 모듈 요약 → 프로젝트 요약
```

**흐름:**
1. `llmcode scan .` → 각 파일 요약 생성 (서버)
2. 요약들을 로컬 SQLite에 저장
3. 질문 시 관련 요약만 컨텍스트에 포함

### 2-2. RAG (Retrieval Augmented Generation)

**임베딩 파이프라인:**
```
파일 청크 → 서버 임베딩 API → 벡터 → ChromaDB (로컬)
```

**검색 흐름:**
```
질문 → 임베딩 → 유사 청크 검색 → 컨텍스트 구성 → LLM
```

**API 추가:**
```http
POST /api/v1/embed
{
  "texts": ["코드 청크1", "코드 청크2"],
  "model": "nomic-embed-text"
}

Response:
{
  "embeddings": [[0.1, 0.2, ...], [0.3, 0.4, ...]]
}
```

### 2-3. 스마트 컨텍스트 구성

질문이 들어오면:
1. 질문 임베딩
2. 벡터 DB에서 top-k 유사 청크 검색
3. 관련 파일 요약 추가
4. 토큰 예산 내에서 컨텍스트 구성
5. LLM에 전송

---

## Phase 3 - 인터랙티브 CLI

### 목표
> Claude Code 같은 대화형 경험

### 기능

```bash
# 프로젝트 스캔 (최초 1회 또는 변경 시)
llmcode scan . --ext .cpp,.h,.hlsl

# 대화형 모드
llmcode chat
> 렌더링 파이프라인 구조 설명해줘
> 이 부분을 Vulkan으로 바꾸려면?
> /include src/vulkan/  # 추가 파일 컨텍스트에 포함
> /clear                # 대화 초기화

# 코드 개선 제안
llmcode improve src/renderer.cpp --focus "성능 최적화"

# diff 기반 재스캔 (빠름)
llmcode scan --diff
```

### 로컬 상태 관리

```
.llmcode/
├── config.json          # 서버 URL, API 키, 설정
├── summaries.db         # 파일/모듈 요약 (SQLite)
├── vectors.db/          # ChromaDB 벡터 저장소
├── history.json         # 대화 히스토리
└── cache/               # 응답 캐시
```

---

## Phase 4 - 고급 기능 (선택)

- [ ] Git diff 기반 증분 스캔
- [ ] 멀티 모델 (요약용 작은 모델, 분석용 큰 모델)
- [ ] 코드 수정 제안 → 직접 적용 (patch 생성)
- [ ] VS Code 확장
- [ ] Claude API fallback (복잡한 질문용)

---

## 기술 스택 요약

| 구분 | 기술 |
|------|------|
| **서버** | FastAPI, Uvicorn, SSE (sse-starlette) |
| **클라이언트** | Click (CLI), httpx (HTTP), ChromaDB (벡터) |
| **인증** | API Key, slowapi (rate limit) |
| **저장** | SQLite (요약), ChromaDB (벡터), JSON (설정) |
| **LLM** | Ollama (deepseek-coder, nomic-embed-text) |

---

## 다음 단계

1. **서버 MVP 구현** - FastAPI + Ollama 연동 + 스트리밍 + 인증
2. **클라이언트 MVP 구현** - CLI + 파일 스캔 + API 호출
3. **E2E 테스트** - 실제 코드로 분석 테스트
4. **Phase 2 진입** - 임베딩 + RAG 구현

---

바로 시작할까?
