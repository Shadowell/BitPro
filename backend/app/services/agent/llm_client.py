"""
通义千问 LLM 客户端封装
兼容 OpenAI Chat Completions API 格式

修复: 复用 httpx.AsyncClient 避免文件描述符泄漏 (Too many open files)
"""
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 2.0


class QwenClient:
    """通义千问 API 客户端 (兼容 OpenAI 格式)"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or settings.QWEN_API_KEY
        self.model = model or settings.QWEN_MODEL
        self.base_url = (base_url or settings.QWEN_BASE_URL).rstrip("/")
        if not self.api_key:
            raise ValueError("QWEN_API_KEY is not configured")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=180)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict[str, str]] = None,
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            body["response_format"] = response_format

        last_error: Optional[Exception] = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                client = await self._get_client()
                resp = await client.post(url, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return content
            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(
                    "Qwen API HTTP %s (attempt %d/%d): %s",
                    e.response.status_code, attempt, _MAX_RETRIES, e.response.text[:300],
                )
                if e.response.status_code == 429 or e.response.status_code >= 500:
                    await asyncio.sleep(_RETRY_DELAY * attempt)
                    continue
                raise
            except (httpx.RequestError, KeyError) as e:
                last_error = e
                logger.warning("Qwen API error (attempt %d/%d): %s", attempt, _MAX_RETRIES, e)
                # 连接错误时重置 client
                await self.close()
                await asyncio.sleep(_RETRY_DELAY * attempt)

        raise RuntimeError(f"Qwen API failed after {_MAX_RETRIES} retries: {last_error}")

    async def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        raw = await self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        text = raw.strip()
        if text.startswith("```"):
            first_nl = text.index("\n")
            text = text[first_nl + 1:]
            if text.endswith("```"):
                text = text[:-3].strip()
        return json.loads(text)


qwen_client: Optional[QwenClient] = None


def get_qwen_client() -> QwenClient:
    global qwen_client
    if qwen_client is None:
        qwen_client = QwenClient()
    return qwen_client
