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
    docs_dir: Path = BASE_DIR / "data" / "docs"
    index_dir: Path = BASE_DIR / "data" / "index"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    # LLM: any OpenAI-compatible chat endpoint
    llm_api_base: str = os.getenv("LLM_API_BASE", "https://generativelanguage.googleapis.com/v1beta/openai/")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "gemini-flash-latest")
    mcp_base_url: str = os.getenv("MCP_BASE_URL", "http://localhost:8001")
    top_k: int = 5
    chunk_size: int = 800
    chunk_overlap: int = 200
    max_context_chars: int = 6000

settings = Settings()
