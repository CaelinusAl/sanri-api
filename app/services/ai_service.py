import os
from openai import OpenAI
from fastapi import HTTPException

def get_client():
    key = (os.getenv("OPENAI_API_KEY") or "").strip()

    if not key:
        raise HTTPException(status_code=500, detail="OPENAI_KEY_MISSING")

    return OpenAI(api_key=key)