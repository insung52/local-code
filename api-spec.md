# Local Code Assistant - API 명세서 v1.0

> 서버 (맥북) API 스펙 정의

---

## 기본 정보

| 항목 | 값 |
|------|-----|
| Base URL | `https://{server}:{port}/api/v1` |
| Content-Type | `application/json` |
| 인증 | `X-API-Key` 헤더 |
| 스트리밍 | Server-Sent Events (SSE) |

---

## 인증

모든 요청에 `X-API-Key` 헤더 필수.

```http
X-API-Key: your-secret-api-key
```

**에러 응답 (인증 실패):**
```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid or missing API key"
  }
}
```

---

## 엔드포인트 목록

| Method | Endpoint | 설명 | 스트리밍 |
|--------|----------|------|----------|
| GET | `/health` | 서버 상태 확인 | No |
| GET | `/models` | 사용 가능한 모델 목록 | No |
| POST | `/analyze` | 코드 분석 (메인) | Yes (SSE) |
| POST | `/summarize` | 파일 요약 생성 | Yes (SSE) |
| POST | `/embed` | 텍스트 임베딩 생성 | No |
| POST | `/chat` | 대화형 질의응답 | Yes (SSE) |

---

## 엔드포인트 상세

### 1. GET `/health`

서버 및 Ollama 상태 확인.

**요청:**
```http
GET /api/v1/health
X-API-Key: xxx
```

**응답:**
```json
{
  "status": "ok",
  "ollama": {
    "status": "connected",
    "version": "0.1.32"
  },
  "loaded_models": ["deepseek-coder-v2:16b", "nomic-embed-text"],
  "memory": {
    "total_gb": 16,
    "available_gb": 8.5
  }
}
```

---

### 2. GET `/models`

사용 가능한 모델 목록 조회.

**요청:**
```http
GET /api/v1/models
X-API-Key: xxx
```

**응답:**
```json
{
  "models": [
    {
      "name": "deepseek-coder-v2:16b",
      "type": "chat",
      "context_length": 131072,
      "size_gb": 8.9
    },
    {
      "name": "nomic-embed-text",
      "type": "embedding",
      "context_length": 8192,
      "size_gb": 0.3
    }
  ]
}
```

---

### 3. POST `/analyze`

코드 파일 분석. SSE 스트리밍 응답.

**요청:**
```http
POST /api/v1/analyze
Content-Type: application/json
X-API-Key: xxx

{
  "files": [
    {
      "path": "src/renderer.cpp",
      "content": "#include <vulkan/vulkan.h>\n...",
      "language": "cpp"
    },
    {
      "path": "src/renderer.h",
      "content": "class Renderer { ... }",
      "language": "cpp"
    }
  ],
  "prompt": "이 렌더러의 병목 지점을 찾아줘",
  "options": {
    "model": "deepseek-coder-v2:16b",
    "temperature": 0.3,
    "max_tokens": 4096
  }
}
```

**요청 스키마:**
```
files[]
  ├─ path: string (필수) - 파일 경로
  ├─ content: string (필수) - 파일 내용
  └─ language: string (선택) - 언어 힌트 (cpp, python, rust, ...)

prompt: string (필수) - 분석 요청

options (선택)
  ├─ model: string (기본값: "deepseek-coder-v2:16b")
  ├─ temperature: float 0.0-1.0 (기본값: 0.3)
  └─ max_tokens: int (기본값: 4096)
```

**응답 (SSE):**
```
Content-Type: text/event-stream

data: {"type": "start", "request_id": "abc123"}

data: {"type": "token", "content": "이"}

data: {"type": "token", "content": " 코드"}

data: {"type": "token", "content": "에서"}

...

data: {"type": "done", "usage": {"prompt_tokens": 1234, "completion_tokens": 567, "total_tokens": 1801}}
```

**SSE 이벤트 타입:**
| type | 설명 | 필드 |
|------|------|------|
| `start` | 스트림 시작 | `request_id` |
| `token` | 토큰 청크 | `content` |
| `error` | 에러 발생 | `code`, `message` |
| `done` | 스트림 완료 | `usage` |

---

### 4. POST `/summarize`

단일 파일 요약 생성. 스캔 시 사용.

**요청:**
```http
POST /api/v1/summarize
Content-Type: application/json
X-API-Key: xxx

{
  "file": {
    "path": "src/renderer.cpp",
    "content": "...",
    "language": "cpp"
  },
  "options": {
    "model": "deepseek-coder-v2:16b",
    "max_summary_length": 500
  }
}
```

**응답 (SSE):**
```
data: {"type": "start", "request_id": "def456"}

data: {"type": "token", "content": "이 파일은"}

...

data: {"type": "done", "usage": {...}, "metadata": {"estimated_tokens": 150}}
```

**요약 결과 예시 (완성된 텍스트):**
```
## src/renderer.cpp

Vulkan 기반 렌더러 구현. 주요 기능:
- 스왑체인 관리
- 커맨드 버퍼 생성
- 프레임 렌더링 루프

의존성: VulkanContext, Pipeline, Buffer
호출 관계: main.cpp에서 초기화, Scene에서 draw 호출
```

---

### 5. POST `/embed`

텍스트 임베딩 벡터 생성. RAG용.

**요청:**
```http
POST /api/v1/embed
Content-Type: application/json
X-API-Key: xxx

{
  "texts": [
    "void Renderer::draw() { ... }",
    "class Pipeline { ... }"
  ],
  "model": "nomic-embed-text"
}
```

**요청 스키마:**
```
texts: string[] (필수) - 임베딩할 텍스트 배열 (최대 100개)
model: string (선택, 기본값: "nomic-embed-text")
```

**응답:**
```json
{
  "embeddings": [
    [0.0123, -0.0456, 0.0789, ...],
    [0.0234, -0.0567, 0.0890, ...]
  ],
  "model": "nomic-embed-text",
  "dimensions": 768,
  "usage": {
    "total_tokens": 156
  }
}
```

---

### 6. POST `/chat`

대화형 질의응답. 히스토리 포함.

**요청:**
```http
POST /api/v1/chat
Content-Type: application/json
X-API-Key: xxx

{
  "messages": [
    {
      "role": "system",
      "content": "당신은 코드 분석 전문가입니다. 다음은 프로젝트 요약입니다:\n..."
    },
    {
      "role": "user",
      "content": "렌더링 파이프라인 구조를 설명해줘"
    },
    {
      "role": "assistant",
      "content": "이 프로젝트의 렌더링 파이프라인은..."
    },
    {
      "role": "user",
      "content": "Vulkan으로 바꾸려면 어디를 수정해야 해?"
    }
  ],
  "context": {
    "files": [
      {"path": "src/renderer.cpp", "content": "..."}
    ],
    "summaries": [
      {"path": "src/pipeline.cpp", "summary": "..."}
    ]
  },
  "options": {
    "model": "deepseek-coder-v2:16b",
    "temperature": 0.3,
    "max_tokens": 4096
  }
}
```

**요청 스키마:**
```
messages[] (필수)
  ├─ role: "system" | "user" | "assistant"
  └─ content: string

context (선택) - 추가 컨텍스트
  ├─ files[]: 전체 파일 내용 (우선순위 높음)
  └─ summaries[]: 파일 요약 (컨텍스트 절약)

options (선택)
  ├─ model: string
  ├─ temperature: float
  └─ max_tokens: int
```

**응답 (SSE):**
```
data: {"type": "start", "request_id": "ghi789"}

data: {"type": "token", "content": "Vulkan"}

...

data: {"type": "done", "usage": {...}}
```

---

## 공통 에러 응답

모든 에러는 다음 형식:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "사람이 읽을 수 있는 메시지",
    "details": {}
  }
}
```

**에러 코드:**

| 코드 | HTTP Status | 설명 |
|------|-------------|------|
| `UNAUTHORIZED` | 401 | API 키 누락/불일치 |
| `RATE_LIMITED` | 429 | 요청 한도 초과 |
| `INVALID_REQUEST` | 400 | 요청 형식 오류 |
| `MODEL_NOT_FOUND` | 404 | 요청한 모델 없음 |
| `MODEL_LOADING` | 503 | 모델 로딩 중 |
| `CONTEXT_TOO_LONG` | 413 | 컨텍스트가 모델 한도 초과 |
| `OLLAMA_ERROR` | 502 | Ollama 서버 오류 |
| `INTERNAL_ERROR` | 500 | 서버 내부 오류 |

**예시:**
```json
{
  "error": {
    "code": "CONTEXT_TOO_LONG",
    "message": "Context exceeds model limit",
    "details": {
      "provided_tokens": 150000,
      "model_limit": 131072,
      "model": "deepseek-coder-v2:16b"
    }
  }
}
```

---

## Rate Limiting

| 항목 | 제한 |
|------|------|
| 요청 수 | 60회/분 |
| 요청 크기 | 10MB |
| 동시 스트림 | 3개 |

**Rate Limit 헤더:**
```http
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1699900000
```

---

## 버전 관리

- API 버전은 URL에 포함 (`/api/v1/...`)
- Breaking change 시 버전 증가 (`v2`)
- 하위 호환 변경은 버전 유지

---

## TODO (구현하면서 추가)

- [ ] WebSocket 지원 (양방향 통신 필요 시)
- [ ] 배치 요약 API (여러 파일 한번에)
- [ ] 모델 프리로드 API
- [ ] 취소 API (진행 중인 요청 취소)
