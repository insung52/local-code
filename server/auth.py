from fastapi import Request, HTTPException, Security
from fastapi.security import APIKeyHeader
from starlette.status import HTTP_401_UNAUTHORIZED

from config import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    request: Request,
    api_key: str = Security(api_key_header),
) -> str:
    """API 키 검증"""
    settings = get_settings()

    # API 키가 설정되지 않았으면 인증 스킵 (개발용)
    if not settings.api_key_list:
        return "dev-mode"

    if not api_key:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Missing API key. Provide X-API-Key header.",
                }
            },
        )

    if api_key not in settings.api_key_list:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Invalid API key.",
                }
            },
        )

    return api_key
