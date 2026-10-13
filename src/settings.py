import os
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CACHE_DIR = PROJECT_ROOT / "artifacts"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

META_DATA_PATH = CACHE_DIR / "meta_data.json"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

DEBUG_PROMPTS_DIR = CACHE_DIR / "debug_prompts"
DEBUG_PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

AST_FUNCTIONS_PATH = CACHE_DIR / "functions_ast.json"
RAW_FUNCTIONS_PATH = CACHE_DIR / "functions_raw.json"
DESCRIBED_FUNCTIONS_PATH = CACHE_DIR / "functions_described.json"
RAG_FUNCTIONS_PATH = CACHE_DIR / "functions_rag.json"

AST_FUNCTIONS_UPD_PATH = CACHE_DIR / "functions_ast_upd.json"
RAW_FUNCTIONS_UPD_PATH = CACHE_DIR / "functions_raw_upd.json"
DESCRIBED_FUNCTIONS_UPD_PATH = CACHE_DIR / "functions_described_upd.json"
RAG_FUNCTIONS_UPD_PATH = CACHE_DIR / "functions_rag_upd.json"

PROMPT_DIR = PROJECT_ROOT / "prompts"
PROMPT_DIR.mkdir(parents=True, exist_ok=True)
TRAINING_PROMPT_PATH = PROMPT_DIR / "training_prompt.txt"
INFERENCE_PROMPT_PATH = PROMPT_DIR / "inference_prompt.txt"

DB_PARAMS = {
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432")
}
CFG = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

if __name__ == "__main__":
    print(PROJECT_ROOT) # debug