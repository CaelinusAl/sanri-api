import os
from openai import OpenAI


_client = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY eksik")
        _client = OpenAI(api_key=api_key)
    return _client


def get_model() -> str:
    model = os.getenv("OPENAI_MODEL", "").strip()
    if not model:
        model = "gpt-4o-mini"
    return model
