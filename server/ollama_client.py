import httpx
from typing import AsyncGenerator, Any
import json

from config import get_settings


class OllamaClient:
    """Ollama API 클라이언트"""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.ollama_base_url

    async def health_check(self) -> dict:
        """Ollama 서버 상태 확인"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/version")
                if response.status_code == 200:
                    return {"status": "connected", "version": response.json().get("version")}
                return {"status": "error", "message": f"Status {response.status_code}"}
        except httpx.ConnectError:
            return {"status": "disconnected", "message": "Cannot connect to Ollama"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def list_models(self) -> list[dict]:
        """로컬에 있는 모델 목록"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200:
                    models = response.json().get("models", [])
                    return [
                        {
                            "name": m["name"],
                            "size_gb": round(m.get("size", 0) / 1e9, 2),
                            "modified_at": m.get("modified_at"),
                        }
                        for m in models
                    ]
                return []
        except Exception:
            return []

    async def generate_stream(
        self,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[dict, None]:
        """스트리밍 텍스트 생성 (generate API)"""
        model = model or self.settings.default_chat_model

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json=payload,
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    yield {"type": "error", "code": "OLLAMA_ERROR", "message": error_text.decode()}
                    return

                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if data.get("done"):
                                yield {
                                    "type": "done",
                                    "usage": {
                                        "prompt_tokens": data.get("prompt_eval_count", 0),
                                        "completion_tokens": data.get("eval_count", 0),
                                        "total_tokens": data.get("prompt_eval_count", 0)
                                        + data.get("eval_count", 0),
                                    },
                                }
                            else:
                                yield {"type": "token", "content": data.get("response", "")}
                        except json.JSONDecodeError:
                            continue

    async def chat_stream(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[dict, None]:
        """스트리밍 채팅 (chat API)"""
        model = model or self.settings.default_chat_model

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload,
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    yield {"type": "error", "code": "OLLAMA_ERROR", "message": error_text.decode()}
                    return

                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if data.get("done"):
                                yield {
                                    "type": "done",
                                    "usage": {
                                        "prompt_tokens": data.get("prompt_eval_count", 0),
                                        "completion_tokens": data.get("eval_count", 0),
                                        "total_tokens": data.get("prompt_eval_count", 0)
                                        + data.get("eval_count", 0),
                                    },
                                }
                            else:
                                content = data.get("message", {}).get("content", "")
                                if content:
                                    yield {"type": "token", "content": content}
                        except json.JSONDecodeError:
                            continue

    async def embed(self, texts: list[str], model: str | None = None) -> dict:
        """텍스트 임베딩 생성"""
        model = model or self.settings.default_embed_model

        embeddings = []
        total_tokens = 0

        async with httpx.AsyncClient(timeout=120.0) as client:
            for text in texts:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": model, "prompt": text},
                )

                if response.status_code != 200:
                    raise Exception(f"Embedding failed: {response.text}")

                data = response.json()
                embeddings.append(data["embedding"])
                # Ollama doesn't return token count for embeddings, estimate it
                total_tokens += len(text.split()) * 2  # rough estimate

        return {
            "embeddings": embeddings,
            "model": model,
            "dimensions": len(embeddings[0]) if embeddings else 0,
            "usage": {"total_tokens": total_tokens},
        }


# 싱글톤 인스턴스
ollama_client = OllamaClient()
