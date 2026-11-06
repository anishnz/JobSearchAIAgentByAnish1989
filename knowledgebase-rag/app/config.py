"""Settings + model-config store for the Knowledge Base (RAG) service.

Taken from the CyberQuest knowledge base (v1.2, 31 Oct 2026) and changed for
JobSearchAIAgentByAnish1989:
  * every user has a PRIVATE knowledge base (owner "c<id>"), plus one "shared" part
    that only the admin can change (job-search tips for everyone)
  * two roles only: "user" and "admin"
  * when started without Docker it reads the project's .env file itself

Model settings (display name / base URL / model ID / key) live in
data/model_config.json so the admin can change them at runtime without a restart.
Everything else comes from environment variables.
"""
import json
import os
import threading
from pathlib import Path

from pydantic import BaseModel

SERVICE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = SERVICE_DIR.parent


def _load_env_file(path: Path) -> None:
    """No-Docker mode: read KEY=VALUE lines from the project .env. Existing variables are never replaced."""
    try:
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except OSError:
        pass


_load_env_file(PROJECT_DIR / ".env")

DATA_DIR = Path(os.getenv("RAG_DATA_DIR", str(PROJECT_DIR / "data" / "rag")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = DATA_DIR / "model_config.json"
# Keep the downloaded search model inside data/rag/hf (Docker sets HF_HOME itself).
os.environ.setdefault("HF_HOME", str(DATA_DIR / "hf"))

# Shared secret between the Django website and this service.
SERVICE_KEY = os.getenv("RAG_SERVICE_KEY", "")
if not SERVICE_KEY:
    raise RuntimeError("RAG_SERVICE_KEY is not set (see .env.example)")

# Embedding model (the chat model cannot do embeddings). Multilingual by default (English, Nepali, Hindi ...).
EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
# Chunks scoring below this cosine similarity are ignored.
MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.2"))
# Loaded once into the SHARED part when the knowledge base is empty, so questions work straight away.
SEED_FILE = Path(os.getenv("RAG_SEED_FILE", str(SERVICE_DIR / "job_search_knowledge_base_NZ.md")))

# Ollama on the laptop (free local AI). Docker: docker-compose sets http://host.docker.internal:11434.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

ROLES = {"user", "admin"}
SHARED_OWNER = "shared"


# First-start defaults: DeepSeek's public OpenAI-compatible API (same as CyberQuest).
# The admin can change all of them on the Knowledge Base page (for example a local
# Ollama: http://localhost:11434/v1). The key can also come from RAG_LLM_API_KEY in .env.
class ModelConfig(BaseModel):
    display_name: str = os.getenv("RAG_LLM_NAME", "DeepSeek")
    base_url: str = os.getenv("RAG_LLM_BASE_URL", "https://api.deepseek.com/v1")
    model_id: str = os.getenv("RAG_LLM_MODEL", "deepseek-chat")
    api_key: str = os.getenv("RAG_LLM_API_KEY", "") or "EMPTY"  # local servers ignore it; DeepSeek needs a real key
    temperature: float = 0.3
    max_tokens: int = 1500
    timeout: int = 120


_lock = threading.Lock()


def load_model_config() -> ModelConfig:
    with _lock:
        if CONFIG_FILE.exists():
            return ModelConfig(**json.loads(CONFIG_FILE.read_text("utf-8")))
    cfg = ModelConfig()
    save_model_config(cfg)
    return cfg


def save_model_config(cfg: ModelConfig) -> None:
    with _lock:
        CONFIG_FILE.write_text(cfg.model_dump_json(indent=2), "utf-8")
        try:
            os.chmod(CONFIG_FILE, 0o600)
        except OSError:
            pass


def public_view(cfg: ModelConfig) -> dict:
    """Config with the API key masked, safe to return to the admin page."""
    d = cfg.model_dump()
    key = d.pop("api_key")
    d["api_key_masked"] = ("*" * 6 + key[-4:]) if len(key) > 4 else "******"
    return d
