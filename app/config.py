import os
from pathlib import Path
from dataclasses import dataclass

BASE_DIR = Path(__file__).resolve().parent.parent

env_path = BASE_DIR / ".env"
if env_path.exists():
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                try:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())
                except ValueError:
                    pass

@dataclass
class Settings:
    # LLM: any OpenAI-compatible chat endpoint
    llm_api_base: str = os.getenv("LLM_API_BASE", "https://generativelanguage.googleapis.com/v1beta/openai/")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "gemini-flash-latest")
    mcp_base_url: str = os.getenv("MCP_BASE_URL", "http://localhost:8001")

settings = Settings()
