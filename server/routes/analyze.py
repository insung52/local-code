from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import json
import uuid

from auth import verify_api_key
from ollama_client import ollama_client
from config import get_settings

router = APIRouter()


class FileInput(BaseModel):
    path: str
    content: str
    language: str | None = None


class AnalyzeOptions(BaseModel):
    model: str | None = None
    temperature: float = 0.3
    max_tokens: int = 4096


class AnalyzeRequest(BaseModel):
    files: list[FileInput]
    prompt: str
    options: AnalyzeOptions | None = None


def build_analyze_prompt(files: list[FileInput], user_prompt: str) -> str:
    """파일들과 사용자 프롬프트를 하나의 프롬프트로 조합"""
    parts = ["다음은 분석할 코드 파일들입니다:\n"]

    for f in files:
        lang = f.language or "unknown"
        parts.append(f"### {f.path} ({lang})\n```{lang}\n{f.content}\n```\n")

    parts.append(f"\n## 요청\n{user_prompt}")

    return "\n".join(parts)


@router.post("/analyze")
async def analyze_code(
    request: AnalyzeRequest,
    api_key: str = Depends(verify_api_key),
):
    """코드 분석 (SSE 스트리밍)"""
    settings = get_settings()
    options = request.options or AnalyzeOptions()

    # 프롬프트 구성
    prompt = build_analyze_prompt(request.files, request.prompt)
    model = options.model or settings.default_chat_model

    request_id = str(uuid.uuid4())[:8]

    async def generate():
        # 시작 이벤트
        yield {"data": json.dumps({"type": "start", "request_id": request_id})}

        try:
            async for chunk in ollama_client.generate_stream(
                prompt=prompt,
                model=model,
                system="당신은 전문 코드 분석가입니다. 주어진 코드를 분석하고 사용자의 질문에 정확하게 답변하세요.",
                temperature=options.temperature,
                max_tokens=options.max_tokens,
            ):
                yield {"data": json.dumps(chunk)}

        except Exception as e:
            yield {
                "data": json.dumps(
                    {"type": "error", "code": "INTERNAL_ERROR", "message": str(e)}
                )
            }

    return EventSourceResponse(generate())


class SummarizeRequest(BaseModel):
    file: FileInput
    options: AnalyzeOptions | None = None


@router.post("/summarize")
async def summarize_file(
    request: SummarizeRequest,
    api_key: str = Depends(verify_api_key),
):
    """파일 요약 생성 (SSE 스트리밍)"""
    settings = get_settings()
    options = request.options or AnalyzeOptions()
    model = options.model or settings.default_chat_model

    lang = request.file.language or "unknown"
    prompt = f"""다음 코드 파일을 요약해주세요.

### {request.file.path} ({lang})
```{lang}
{request.file.content}
```

다음 형식으로 요약해주세요:
1. 파일의 주요 목적 (1-2문장)
2. 주요 클래스/함수 목록
3. 의존성 (import/include)
4. 다른 파일과의 관계 (있다면)

간결하게 작성하세요."""

    request_id = str(uuid.uuid4())[:8]

    async def generate():
        yield {"data": json.dumps({"type": "start", "request_id": request_id})}

        try:
            async for chunk in ollama_client.generate_stream(
                prompt=prompt,
                model=model,
                system="당신은 코드 요약 전문가입니다. 간결하고 정확하게 요약하세요.",
                temperature=0.2,  # 요약은 더 결정적으로
                max_tokens=options.max_tokens,
            ):
                yield {"data": json.dumps(chunk)}

        except Exception as e:
            yield {
                "data": json.dumps(
                    {"type": "error", "code": "INTERNAL_ERROR", "message": str(e)}
                )
            }

    return EventSourceResponse(generate())
