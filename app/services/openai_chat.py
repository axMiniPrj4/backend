"""
OpenAI (or compatible) chat completion helper for AI assistant replies.
OPENAI_API_KEY 가 없으면 None을 반환 → 라우터에서 가응답 사용.
"""
from __future__ import annotations

import httpx

from app.core.config import settings

_SYSTEM = (
    "당신은 오합지졸.io 프로젝트 협업 도우미입니다. "
    "한국어로 짧고 명확하게 답하세요. 불확실한 내용은 추측하지 말고 확인을 요청하세요."
)


def generate_assistant_reply(user_content: str, history: list[dict] | None = None) -> str | None:
    """Returns assistant text, or None when API key is missing / call fails."""
    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        return None

    messages: list[dict] = [{"role": "system", "content": _SYSTEM}]
    for item in history or []:
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": str(content)})
    messages.append({"role": "user", "content": user_content})

    base = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
    url = f"{base}/chat/completions"
    payload = {
        "model": settings.openai_model or "gpt-4o-mini",
        "messages": messages,
        "temperature": 0.4,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=45.0) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            return (text or "").strip() or None
    except Exception:
        return None
