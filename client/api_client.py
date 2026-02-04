import httpx
from typing import AsyncGenerator, List, Optional
import json


class APIClient:
    """서버 API 클라이언트"""

    def __init__(self, server_url: str, api_key: str):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.timeout = httpx.Timeout(300.0, connect=10.0)

    def _headers(self) -> dict:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    async def health_check(self) -> dict:
        """서버 상태 확인"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.server_url}/api/v1/health",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    async def list_models(self) -> List[dict]:
        """모델 목록 조회"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.server_url}/api/v1/models",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json().get("models", [])

    async def _stream_sse(
        self,
        method: str,
        url: str,
        payload: dict,
    ) -> AsyncGenerator[dict, None]:
        """SSE 스트림 파싱"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                method,
                url,
                headers=self._headers(),
                json=payload,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    line = line.strip()
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str:
                            try:
                                yield json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

    async def analyze_stream(
        self,
        files: List[dict],
        prompt: str,
        model: Optional[str] = None,
    ) -> AsyncGenerator[dict, None]:
        """코드 분석 (스트리밍)"""
        payload = {
            "files": files,
            "prompt": prompt,
        }

        if model:
            payload["options"] = {"model": model}

        async for chunk in self._stream_sse(
            "POST",
            f"{self.server_url}/api/v1/analyze",
            payload,
        ):
            yield chunk

    async def chat_stream(
        self,
        messages: List[dict],
        context: Optional[dict] = None,
        model: Optional[str] = None,
    ) -> AsyncGenerator[dict, None]:
        """대화형 질의응답 (스트리밍)"""
        payload = {
            "messages": messages,
        }

        if context:
            payload["context"] = context

        if model:
            payload["options"] = {"model": model}

        async for chunk in self._stream_sse(
            "POST",
            f"{self.server_url}/api/v1/chat",
            payload,
        ):
            yield chunk

    async def summarize_stream(
        self,
        file: dict,
        model: Optional[str] = None,
    ) -> AsyncGenerator[dict, None]:
        """파일 요약 (스트리밍)"""
        payload = {
            "file": file,
        }

        if model:
            payload["options"] = {"model": model}

        async for chunk in self._stream_sse(
            "POST",
            f"{self.server_url}/api/v1/summarize",
            payload,
        ):
            yield chunk

    async def embed(
        self,
        texts: List[str],
        model: Optional[str] = None,
    ) -> dict:
        """텍스트 임베딩"""
        payload = {
            "texts": texts,
        }

        if model:
            payload["model"] = model

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.server_url}/api/v1/embed",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()
