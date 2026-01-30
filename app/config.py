from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseModel):
    openai_api_key: str
    openai_model: str
    data_dir: str = "data"
    static_dir: str = "static"
    voices_dir: str = "static/voices"
    # OpenAI text to speech guide: built-in voices exist; model name may evolve.
    # We keep a default that is commonly used in the docs.
    tts_model: str = "gpt-4o-mini-tts"

def get_settings() -> Settings:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "").strip()

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing in environment")
    if not model:
        raise RuntimeError("OPENAI_MODEL is missing in environment")

    return Settings(openai_api_key=api_key, openai_model=model)