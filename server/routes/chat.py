from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import json
import uuid

from auth import verify_api_key
from ollama_client import ollama_client
from config import get_settings

router = APIRouter()


class Message(BaseModel):
    role: str  # "system", "user", "assistant"
    content: str


class FileContext(BaseModel):
    path: str
    content: str


class SummaryContext(BaseModel):
    path: str
    summary: str


class ChatContext(BaseModel):
    files: list[FileContext] | None = None
    summaries: list[SummaryContext] | None = None


class ChatOptions(BaseModel):
    model: str | None = None
    temperature: float = 0.3
    max_tokens: int = 4096


class ChatRequest(BaseModel):
    messages: list[Message]
    context: ChatContext | None = None
    options: ChatOptions | None = None


def build_messages_with_context(
    messages: list[Message], context: ChatContext | None
) -> list[dict]:
    """메시지에 컨텍스트 추가"""
    result = []

    # 시스템 메시지 찾기
    system_content = "당신은 전문 코드 분석가입니다."
    other_messages = []

    for msg in messages:
        if msg.role == "system":
            system_content = msg.content
        else:
            other_messages.append(msg)

    # 컨텍스트가 있으면 시스템 메시지에 추가
    if context:
        context_parts = [system_content, "\n\n## 프로젝트 컨텍스트\n"]

        if context.summaries:
            context_parts.append("### 파일 요약\n")
            for s in context.summaries:
                context_parts.append(f"**{s.path}**: {s.summary}\n")

        if context.files:
            context_parts.append("\n### 참조 파일\n")
            for f in context.files:
                context_parts.append(f"**{f.path}**:\n```\n{f.content}\n```\n")

        system_content = "".join(context_parts)

    result.append({"role": "system", "content": system_content})

    # 나머지 메시지 추가
    for msg in other_messages:
        result.append({"role": msg.role, "content": msg.content})

    return result


@router.post("/chat")
async def chat(
    request: ChatRequest,
    api_key: str = Depends(verify_api_key),
):
    """대화형 질의응답 (SSE 스트리밍)"""
    settings = get_settings()
    options = request.options or ChatOptions()
    model = options.model or settings.default_chat_model

    # 메시지 구성
    messages = build_messages_with_context(request.messages, request.context)

    request_id = str(uuid.uuid4())[:8]

    async def generate():
        yield {"data": json.dumps({"type": "start", "request_id": request_id})}

        try:
            async for chunk in ollama_client.chat_stream(
                messages=messages,
                model=model,
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
