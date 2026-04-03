import json
import os
import re
from typing import Any, Dict

from openai import OpenAI
from fastapi import HTTPException


def get_client() -> OpenAI:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()

    if not key:
        raise HTTPException(status_code=500, detail="OPENAI_KEY_MISSING")

    return OpenAI(api_key=key)


def generate_sanri_response(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_input: str,
) -> str:
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
        temperature=0.9,
        max_tokens=500,
    )

    text_resp = (completion.choices[0].message.content or "").strip()

    if not text_resp:
        text_resp = "Sanrı seni duydu."

    return text_resp


def _strip_json_fence(raw: str) -> str:
    t = (raw or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def generate_kod_okuma_json(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_input: str,
    max_tokens: int = 1600,
) -> Dict[str, Any]:
    """
    Üst Bilinç Kodlama — yalnızca JSON nesnesi (OpenAI json_object).
    """
    kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
        temperature=0.88,
        max_tokens=max_tokens,
    )
    try:
        completion = client.chat.completions.create(
            **kwargs,
            response_format={"type": "json_object"},
        )
    except Exception:
        completion = client.chat.completions.create(**kwargs)

    raw = (completion.choices[0].message.content or "").strip()
    raw = _strip_json_fence(raw)
    if not raw:
        raise ValueError("EMPTY_COMPLETION")

    return json.loads(raw)