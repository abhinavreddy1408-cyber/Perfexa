import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

# Models
# Fast/smaller model for intent extraction, synthetic payloads, and post-run summary
MODEL_FAST = os.getenv("MODEL_FAST", "meta/llama-3.2-11b-vision-instruct")
# Coding model for k6 JavaScript script synthesis
MODEL_CODE = os.getenv("MODEL_CODE", "meta/llama-3.2-11b-vision-instruct")

# App ports & URLs
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
TARGET_APP_URL = os.getenv("TARGET_APP_URL", "http://localhost:8001")
LOCAL_TARGET_APP_URL = os.getenv("LOCAL_TARGET_APP_URL", "http://localhost:8001")

# Storage paths
LOGS_DIR = BASE_DIR / "logs"
TEST_RUNS_DIR = BASE_DIR / "test_runs"
DATA_DIR = BASE_DIR / "backend" / "data"
TOOLS_BIN_DIR = BASE_DIR / "tools" / "bin"

LOGS_DIR.mkdir(parents=True, exist_ok=True)
TEST_RUNS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
TOOLS_BIN_DIR.mkdir(parents=True, exist_ok=True)

RAW_LLM_LOG_PATH = LOGS_DIR / "llm_raw_calls.jsonl"
SQLITE_DB_PATH = DATA_DIR / "test_runs.db"
DATABASE_URL = f"sqlite+aiosqlite:///{SQLITE_DB_PATH.as_posix()}"
