"""OpenAI 음성 API 공통 호출(STT·TTS). 키는 요청 머리말에만 쓰고 로그에 남기지 않는다."""

import logging
from typing import Any

import httpx2
from pydantic import SecretStr

from app.errors import AppError

logger = logging.getLogger("trailtalk.voice")


def unavailable() -> AppError:
    return AppError("voice_unavailable", "음성 서비스를 쓸 수 없습니다.", 503)


def failed(prefix: str) -> AppError:
    return AppError(f"{prefix}_failed", "음성 처리에 실패했습니다.", 502)


def _error_field(response: httpx2.Response, field: str) -> str | None:
    try:
        return response.json()["error"][field]
    except (ValueError, KeyError, TypeError):
        return None


def _error_type(response: httpx2.Response) -> str | None:
    return _error_field(response, "type")


def _error_code(response: httpx2.Response) -> str | None:
    return _error_field(response, "code")


async def post(
    client: httpx2.AsyncClient,
    *,
    base_url: str,
    api_key: SecretStr | None,
    path: str,
    timeout_s: float,
    error_prefix: str,
    **kwargs: Any,
) -> httpx2.Response:
    """POST 후 성공 응답을 돌려준다. 실패는 {prefix}_timeout·{prefix}_failed·voice_unavailable."""
    if api_key is None or not api_key.get_secret_value():
        logger.error("OPENAI_API_KEY가 설정되지 않았습니다")
        raise unavailable()
    headers = {"Authorization": f"Bearer {api_key.get_secret_value()}"}
    url = base_url.rstrip("/") + path
    try:
        response = await client.post(url, headers=headers, timeout=timeout_s, **kwargs)
    except httpx2.TimeoutException as exc:
        raise AppError(f"{error_prefix}_timeout", "음성 처리 시간이 초과되었습니다.", 504) from exc
    except httpx2.HTTPError as exc:
        logger.warning("%s 요청 실패: %s", path, type(exc).__name__)
        raise failed(error_prefix) from exc
    if response.status_code >= 400:
        if response.status_code in (401, 403):
            # 인증 오류 본문에는 키 뒷자리가 들어 있어 종류만 남긴다
            detail = f"{_error_type(response)}/{_error_code(response)}"
        else:
            detail = response.text[:500].replace("\n", " ")
        logger.warning("%s 오류 %s: %s", path, response.status_code, detail)
        # 키 오류·크레딧 소진은 다시 시도해도 풀리지 않는다
        if response.status_code in (401, 403) or _error_type(response) == "insufficient_quota":
            raise unavailable()
        raise failed(error_prefix)
    return response
