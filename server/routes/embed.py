from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import verify_api_key
from ollama_client import ollama_client
from config import get_settings

router = APIRouter()


class EmbedRequest(BaseModel):
    texts: list[str]
    model: str | None = None


@router.post("/embed")
async def create_embeddings(
    request: EmbedRequest,
    api_key: str = Depends(verify_api_key),
):
    """텍스트 임베딩 생성"""
    if not request.texts:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "texts array cannot be empty",
                }
            },
        )

    if len(request.texts) > 100:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "Maximum 100 texts per request",
                }
            },
        )

    settings = get_settings()
    model = request.model or settings.default_embed_model

    try:
        result = await ollama_client.embed(request.texts, model)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={
                "error": {
                    "code": "OLLAMA_ERROR",
                    "message": str(e),
                }
            },
        )
