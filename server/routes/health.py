from fastapi import APIRouter, Depends
import psutil

from auth import verify_api_key
from ollama_client import ollama_client

router = APIRouter()


@router.get("/health")
async def health_check(api_key: str = Depends(verify_api_key)):
    """서버 및 Ollama 상태 확인"""
    ollama_status = await ollama_client.health_check()
    models = await ollama_client.list_models()

    # 메모리 정보
    memory = psutil.virtual_memory()

    return {
        "status": "ok",
        "ollama": ollama_status,
        "loaded_models": [m["name"] for m in models],
        "memory": {
            "total_gb": round(memory.total / 1e9, 1),
            "available_gb": round(memory.available / 1e9, 1),
        },
    }


@router.get("/models")
async def list_models(api_key: str = Depends(verify_api_key)):
    """사용 가능한 모델 목록"""
    models = await ollama_client.list_models()

    # 모델 타입 추론 (이름 기반)
    result = []
    for m in models:
        model_type = "chat"
        if "embed" in m["name"].lower():
            model_type = "embedding"

        result.append(
            {
                "name": m["name"],
                "type": model_type,
                "size_gb": m["size_gb"],
            }
        )

    return {"models": result}
